"""Один провайдер: OpenAI-совместимый Chat Completions (httpx)."""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Не логировать ключи и длинные тела ответов целиком
_REDACT_BEARER = re.compile(r"(Bearer\s+)([^\s'\"]+)", re.IGNORECASE)
_REDACT_SK = re.compile(r"\b(sk-[a-zA-Z0-9_-]{12,})\b")


def _redact_secrets(text: str, max_len: int = 800) -> str:
    if not text:
        return ""
    t = _REDACT_BEARER.sub(r"\1***", text)
    t = _REDACT_SK.sub("sk-***", t)
    if len(t) > max_len:
        return t[:max_len] + "…"
    return t


def _api_key() -> str:
    key = (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "Не задан ключ API: задайте LLM_API_KEY или OPENAI_API_KEY в окружении или .env"
        )
    return key


def _timeout_sec() -> float:
    raw = os.getenv("LLM_TIMEOUT_SEC") or os.getenv("OPENAI_TIMEOUT_SEC") or "120"
    return max(5.0, float(raw))


def _max_output_tokens() -> int:
    # JSON-анализ с column_roles и feature_ideas часто не укладывается в 4k — обрезка → «Unterminated string».
    raw = os.getenv("LLM_MAX_OUTPUT_TOKENS") or os.getenv("MAX_COMPLETION_TOKENS") or "8192"
    return max(1, min(int(float(raw)), 128_000))


def _token_retry_budgets(base: int) -> list[int]:
    """Возрастающие лимиты для повторов при обрезке ответа (finish_reason=length / битый JSON)."""
    cap = 128_000
    u = max(1, min(int(base), cap))
    out: list[int] = [u]
    step2 = min(cap, max(u * 2, 12_000))
    if step2 > out[-1]:
        out.append(step2)
    step3 = min(cap, max(u * 3, 28_000))
    if step3 > out[-1]:
        out.append(step3)
    return out


def _looks_like_truncated_json_error(exc: BaseException) -> bool:
    msg = (getattr(exc, "msg", None) or str(exc)).lower()
    needles = (
        "unterminated string",
        "unterminated",
        "expecting ',' delimiter",
        "expecting value",
        "expecting property name",
        "invalid \\u",
    )
    return any(n in msg for n in needles)


def _base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def _model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _explicit_llm_proxy_url() -> str | None:
    """Явный прокси только для запросов LLM (перекрывает типичные проблемы с HTTPS_PROXY без пароля → 407)."""
    for key in ("LLM_PROXY", "LLM_HTTPS_PROXY"):
        v = (os.getenv(key) or "").strip()
        if v:
            return v
    return None


def _http_client(timeout: httpx.Timeout) -> httpx.Client:
    """
    trust_env=True подхватывает HTTP(S)_PROXY из окружения.
    Если задан LLM_PROXY — используется он; при LLM_IGNORE_SYSTEM_PROXY=1 отключаем чтение системных прокси,
    чтобы не смешивать их с явным URL (частый случай 407: в системе прокси без логина).
    """
    explicit = _explicit_llm_proxy_url()
    ignore_system = (os.getenv("LLM_IGNORE_SYSTEM_PROXY") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    if explicit:
        return httpx.Client(
            timeout=timeout,
            proxy=explicit,
            trust_env=not ignore_system,
        )
    return httpx.Client(timeout=timeout, trust_env=True)


def _proxy_auth_hint_message(exc: BaseException) -> str:
    msg = str(exc).lower()
    if "407" in msg or "proxy authentication" in msg:
        return (
            " Прокси требует авторизацию: задайте в `.env` переменную "
            "`LLM_PROXY` с учётными данными в URL, например "
            "`LLM_PROXY=http://USER:PASSWORD@proxy.company.com:8080` "
            "(спецсимволы в пароле лучше URL-кодировать). "
            "Если в системе уже задан `HTTPS_PROXY` без пароля и из‑за этого 407, добавьте "
            "`LLM_IGNORE_SYSTEM_PROXY=1` и укажите только `LLM_PROXY` с логином."
        )
    return ""


def _extra_provider_headers() -> dict[str, str]:
    """Доп. заголовки для совместимости (например OpenRouter: HTTP-Referer, X-Title)."""
    out: dict[str, str] = {}
    site = (os.getenv("OPENROUTER_SITE_URL") or os.getenv("HTTP_REFERER") or "").strip()
    if site:
        out["HTTP-Referer"] = site
    title = (os.getenv("OPENROUTER_APP_TITLE") or os.getenv("X_TITLE") or "").strip()
    if title:
        out["X-Title"] = title
    return out


def _json_mode_probably_unsupported(status: int, body: str) -> bool:
    if status not in (400, 404, 422):
        return False
    b = body.lower()
    needles = (
        "response_format",
        "json_object",
        "unknown parameter",
        "unsupported",
        "not supported",
    )
    return any(n in b for n in needles)


def _strip_markdown_json_fence(text: str) -> str:
    t = text.strip()
    if not t.startswith("```"):
        return t
    first_nl = t.find("\n")
    if first_nl != -1:
        t = t[first_nl + 1 :]
    t = t.strip()
    if t.endswith("```"):
        t = t[: -3].strip()
    return t


_TRAILING_COMMA = re.compile(r",(\s*[\}\]])")


def _drop_trailing_commas(s: str) -> str:
    """Лишние запятые перед } или ] — частая ошибка вывода LLM."""
    prev = None
    out = s
    while prev != out:
        prev = out
        out = _TRAILING_COMMA.sub(r"\1", out)
    return out


def _extract_balanced_json_object(s: str, start: int) -> str | None:
    """Вырезает объект {...} с позиции start (символ '{'), учитывая строки в двойных кавычках."""
    if start >= len(s) or s[start] != "{":
        return None
    depth = 0
    i = start
    in_string = False
    escape = False
    n = len(s)
    while i < n:
        c = s[i]
        if not in_string:
            if c == '"':
                in_string = True
                escape = False
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
        else:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
        i += 1
    return None


_EMPTY_AFTER_COLON = re.compile(r":\s*,")


def _fix_empty_json_values(s: str) -> str:
    """`\"key\": ,` или `: ,` — подставляем null (частая ошибка LLM → Expecting value)."""
    prev = None
    out = s
    while prev != out:
        prev = out
        out = _EMPTY_AFTER_COLON.sub(": null,", out)
    return out


def _try_json_repair_lib(s: str) -> dict[str, Any] | None:
    """Библиотека json-repair чинит обрывки, лишние запятые, кавычки и т.д."""
    try:
        from json_repair import repair_json
    except ImportError:
        return None
    try:
        repaired = repair_json(s)
    except Exception:
        return None
    if isinstance(repaired, dict):
        return repaired
    if isinstance(repaired, str):
        for variant in (repaired, _drop_trailing_commas(repaired), _fix_empty_json_values(repaired)):
            try:
                obj = json.loads(variant)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def _gather_json_candidates(t: str) -> list[str]:
    """Полный текст + каждый сбалансированный {...} по всем вхождениям «{»."""
    seen: set[str] = set()
    out: list[str] = []

    def add(s: str) -> None:
        x = s.strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)

    add(t)
    for m in re.finditer(r"\{", t):
        blob = _extract_balanced_json_object(t, m.start())
        if blob:
            add(blob)
    return out


def _variant_strings(s: str) -> list[str]:
    """Цепочки правок без раздувания комбинаторики."""
    seen: set[str] = set()
    variants: list[str] = []

    def add(x: str) -> None:
        if x not in seen:
            seen.add(x)
            variants.append(x)

    add(s)
    add(_drop_trailing_commas(s))
    add(_fix_empty_json_values(s))
    add(_drop_trailing_commas(_fix_empty_json_values(s)))
    add(_fix_empty_json_values(_drop_trailing_commas(s)))
    return variants


def _try_literal_eval_dict(s: str) -> dict[str, Any] | None:
    """Модели часто выводят объект в стиле Python ({'a': 1}) — ast.literal_eval безопасен для литералов."""
    s = s.strip()
    if not s.startswith("{"):
        return None
    try:
        v = ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return None
    return v if isinstance(v, dict) else None


_ANALYSIS_ROOT_KEYS = frozenset({"dataset_summary", "column_roles", "feature_ideas"})
_MAX_UNWRAP_DEPTH = 10


def _unwrap_analysis_json_root(obj: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """
    Модели и провайдеры часто кладут контрактный JSON внутрь обёртки
    (result / data / analysis / output и т.д.) или в строку с JSON.
    Без распаковки нормализация обнуляет поля → пустой UI.
    """
    if depth > _MAX_UNWRAP_DEPTH or not isinstance(obj, dict):
        return obj if isinstance(obj, dict) else {}
    if _ANALYSIS_ROOT_KEYS <= obj.keys():
        return obj
    for v in obj.values():
        if isinstance(v, dict):
            inner = _unwrap_analysis_json_root(v, depth + 1)
            if _ANALYSIS_ROOT_KEYS <= inner.keys():
                return inner
    for v in obj.values():
        if isinstance(v, str):
            s = v.strip()
            if not s.startswith("{") or "dataset_summary" not in s:
                continue
            parsed: dict[str, Any] | None = None
            try:
                loaded = json.loads(s)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                repaired = _try_json_repair_lib(s)
                if isinstance(repaired, dict):
                    parsed = repaired
            if parsed is not None:
                inner = _unwrap_analysis_json_root(parsed, depth + 1)
                if _ANALYSIS_ROOT_KEYS <= inner.keys():
                    return inner
    return obj


def _analysis_parse_score(obj: dict[str, Any]) -> int:
    """Чем выше — тем ближе объект к ожидаемому контракту (для выбора среди нескольких {...})."""
    u = _unwrap_analysis_json_root(dict(obj))
    if not (_ANALYSIS_ROOT_KEYS <= u.keys()):
        return -1
    ds, cr, fi = u.get("dataset_summary"), u.get("column_roles"), u.get("feature_ideas")
    if not isinstance(ds, dict) or not isinstance(cr, list) or not isinstance(fi, list):
        return -1
    return 20 + min(len(ds), 80) * 5 + min(len(cr), 500) * 3 + min(len(fi), 500) * 3


def _parse_json_object(text: str) -> dict[str, Any]:
    """
    Разбор ответа модели в один объект: строгий JSON, хвостовые запятые, пустые значения после «:»,
    все вхождения {...}, ast.literal_eval, библиотека json-repair.
    """
    t = _strip_markdown_json_fence(text).strip().lstrip("\ufeff")
    if not t:
        raise json.JSONDecodeError("Пустой ответ модели (нет текста для JSON)", "", 0)

    candidates = _gather_json_candidates(t)
    errors: list[str] = []
    best: dict[str, Any] | None = None
    best_score = -(10**9)

    def consider(obj: dict[str, Any]) -> None:
        nonlocal best, best_score
        sc = _analysis_parse_score(obj)
        if sc > best_score:
            best_score = sc
            best = obj

    for cand in candidates:
        variants = _variant_strings(cand)

        for variant in variants:
            try:
                obj = json.loads(variant)
                if isinstance(obj, dict):
                    consider(obj)
                    continue
            except json.JSONDecodeError as e:
                errors.append(e.msg)

            le = _try_literal_eval_dict(variant)
            if le is not None:
                logger.warning(
                    "LLM ответ разобран как Python-литерал (например одинарные кавычки у ключей)"
                )
                consider(le)
                continue

            repaired = _try_json_repair_lib(variant)
            if repaired is not None:
                logger.warning("LLM JSON восстановлен через json-repair")
                consider(repaired)

    if best is not None:
        return best

    start = t.find("{")
    if start == -1:
        raise json.JSONDecodeError(
            "В тексте нет объекта `{...}`; последние ошибки парсера: " + "; ".join(errors[:8]),
            t,
            0,
        )

    decoder = json.JSONDecoder()
    try:
        obj, _end = decoder.raw_decode(t[start:])
    except json.JSONDecodeError as e:
        hint = errors[-1] if errors else e.msg
        raise json.JSONDecodeError(
            f"Не удалось разобрать JSON: {e.msg}. ({hint}). "
            "Частые причины: обрезанный ответ (увеличьте LLM_MAX_OUTPUT_TOKENS), лишний текст вокруг JSON, "
            "или модель вывела неполный объект.",
            t,
            e.pos + start,
        ) from e
    if not isinstance(obj, dict):
        raise json.JSONDecodeError("Корень JSON не объект", t, start)
    consider(obj)
    assert best is not None
    return best


def _normalize_llm_analysis_json(obj: dict[str, Any]) -> dict[str, Any]:
    """
    Ожидаемые ключи: dataset_summary, column_roles, feature_ideas.
    Заполняет пропуски и учитывает типичные camelCase-варианты от моделей.
    """
    out: dict[str, Any] = dict(_unwrap_analysis_json_root(dict(obj)))

    if not isinstance(out.get("dataset_summary"), dict) and isinstance(out.get("datasetSummary"), dict):
        out["dataset_summary"] = out.pop("datasetSummary")

    ds = out.get("dataset_summary")
    if isinstance(ds, str):
        s = ds.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, dict):
                    out["dataset_summary"] = parsed
                    ds = parsed
            except json.JSONDecodeError:
                pass

    if not isinstance(ds, dict):
        if ds is not None:
            logger.warning("LLM: dataset_summary не объект — подставлен пустой объект")
        out["dataset_summary"] = {}

    if not isinstance(out.get("column_roles"), list) and isinstance(out.get("columnRoles"), list):
        out["column_roles"] = out.pop("columnRoles")

    cr = out.get("column_roles")
    if isinstance(cr, str):
        s = cr.strip()
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    out["column_roles"] = parsed
                    cr = parsed
            except json.JSONDecodeError:
                pass

    if not isinstance(cr, list):
        if cr is not None:
            logger.warning("LLM: column_roles не массив — подставлен []")
        out["column_roles"] = []

    if not isinstance(out.get("feature_ideas"), list):
        for alt in ("featureIdeas", "feature_suggestions", "suggested_features", "features_ideas"):
            if isinstance(out.get(alt), list):
                out["feature_ideas"] = out.pop(alt)
                break

    fi = out.get("feature_ideas")
    if isinstance(fi, str):
        s = fi.strip()
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    out["feature_ideas"] = parsed
                    fi = parsed
            except json.JSONDecodeError:
                pass

    if not isinstance(fi, list):
        if fi is not None:
            logger.warning("LLM: feature_ideas не массив — подставлен []")
        else:
            logger.warning("LLM: в ответе не было feature_ideas — подставлен []")
        out["feature_ideas"] = []

    return out


def _response_looks_like_html(body: str) -> bool:
    s = body.lstrip()[:800].lower()
    return s.startswith("<!doctype") or s.startswith("<html") or "<html" in s[:200]


def _human_http_error(response: httpx.Response) -> str:
    """Короткое сообщение пользователю без дампа HTML-страницы целиком."""
    status = response.status_code
    body = response.text or ""
    base = _base_url()
    url_expected = f"{base}/chat/completions"

    if _response_looks_like_html(body):
        return (
            f"HTTP {status}: сервер вернул HTML (страницу сайта), а не JSON API. "
            f"Обычно это неверный **OPENAI_BASE_URL**. Сейчас используется база `{base}` → запрос уходит на `{url_expected}`. "
            "Для **OpenRouter** в `.env` должно быть: `OPENAI_BASE_URL=https://openrouter.ai/api/v1` "
            "(обязательно суффикс `/api/v1`, без слэша на конце базы). "
            "Частая ошибка — указать только `https://openrouter.ai`."
        )

    snippet = _redact_secrets(body[:500])
    return f"Ошибка API ({status}): {snippet}"


def _assistant_message_text_with_finish(data: dict[str, Any], *, context: str) -> tuple[str, str | None]:
    """
    Достаёт текст ответа ассистента и finish_reason из JSON Chat Completions.
    context — метка для логов: «json mode», «plain», «chat_completion».
    """
    err = data.get("error")
    if isinstance(err, dict):
        msg = err.get("message") or err.get("type") or json.dumps(err, ensure_ascii=False)[:400]
        logger.error("LLM %s: error object in body: %s", context, _redact_secrets(str(msg)))
        raise RuntimeError(
            "Ответ API содержит поле error (ошибка на стороне провайдера): "
            + _redact_secrets(str(msg)[:600])
        )

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        keys = sorted(data.keys())
        logger.error(
            "LLM %s: missing or empty choices; keys=%s snippet=%s",
            context,
            keys,
            _redact_secrets(json.dumps(data, ensure_ascii=False)[:800]),
        )
        raise RuntimeError(
            "Провайдер вернул ответ без choices (нет текста ответа). "
            f"Ключи в JSON: {', '.join(keys)}. "
            "Это не лечится промптом: проверьте OPENAI_BASE_URL, имя модели (OPENAI_MODEL), ключ и лимиты; "
            "при прокси — что до клиента доходит полный JSON от /chat/completions."
        )

    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("Некорректный формат choices[0] в ответе API")

    fr_raw = first.get("finish_reason")
    finish_reason = fr_raw.strip() if isinstance(fr_raw, str) and fr_raw.strip() else None

    message = first.get("message")
    if not isinstance(message, dict):
        message = {}

    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        logger.warning("LLM %s: model refusal: %s", context, _redact_secrets(refusal[:500]))
        raise RuntimeError(
            "Модель отказалась отвечать (refusal). Смягчите или сократите входной профиль и попробуйте снова."
        )

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip(), finish_reason
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                t = p.get("text")
                if isinstance(t, str):
                    parts.append(t)
        joined = "".join(parts).strip()
        if joined:
            return joined, finish_reason

    legacy = first.get("text")
    if isinstance(legacy, str) and legacy.strip():
        return legacy.strip(), finish_reason

    logger.error(
        "LLM %s: empty assistant text finish_reason=%s message_keys=%s",
        context,
        finish_reason,
        list(message.keys()) if isinstance(message, dict) else None,
    )
    raise RuntimeError(
        "Пустой текст ответа модели (content отсутствует или пуст). "
        f"finish_reason={finish_reason!r}. Попробуйте другую модель или увеличьте LLM_MAX_OUTPUT_TOKENS."
    )


def _assistant_message_text(data: dict[str, Any], *, context: str) -> str:
    text, _finish = _assistant_message_text_with_finish(data, context=context)
    return text


def _post_chat(
    *,
    payload: dict[str, Any],
    timeout_sec: float,
) -> httpx.Response:
    url = f"{_base_url()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        **_extra_provider_headers(),
    }
    timeout = httpx.Timeout(timeout_sec, connect=15.0)
    with _http_client(timeout) as client:
        return client.post(url, headers=headers, json=payload)


def chat_completion(
    *,
    system: str,
    user: str,
    temperature: float = 0.4,
    timeout_sec: float | None = None,
    json_object: bool = False,
) -> str:
    """Синхронный вызов chat completions; возвращает текст ответа ассистента."""
    t_out = timeout_sec if timeout_sec is not None else _timeout_sec()
    model = _model()
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": _max_output_tokens(),
    }
    if json_object:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = _post_chat(payload=payload, timeout_sec=t_out)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = _redact_secrets(response.text[:1200] if response.text else "")
        logger.error(
            "LLM HTTP error: status=%s model=%s url_suffix=/chat/completions body=%s",
            response.status_code,
            model,
            detail,
        )
        raise RuntimeError(_human_http_error(response)) from e
    except httpx.RequestError as e:
        logger.error("LLM request failed: %s", type(e).__name__, exc_info=True)
        raise RuntimeError(
            f"Сетевая ошибка при вызове LLM: {e}" + _proxy_auth_hint_message(e)
        ) from e

    try:
        data = response.json()
    except json.JSONDecodeError as e:
        logger.error("LLM response is not JSON: %s", _redact_secrets(response.text[:500]))
        raise RuntimeError("Ответ API не является JSON") from e

    if not isinstance(data, dict):
        raise RuntimeError("Ответ API: ожидался JSON-объект с полем choices")
    return _assistant_message_text(data, context="chat_completion")


def _request_llm_analysis_raw_string(
    *,
    system: str,
    user: str,
    temperature: float,
    timeout_sec: float,
    model: str,
    max_tokens: int,
) -> tuple[str, str | None, bool]:
    """
    Один HTTP-раунд: сначала response_format=json_object, при отказе API — обычный chat.
    Возвращает (текст ответа ассистента, finish_reason, json_object_использовался).
    """
    payload_json: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    raw: str | None = None
    used_json_mode = False
    finish_reason: str | None = None

    try:
        response = _post_chat(payload=payload_json, timeout_sec=timeout_sec)
    except httpx.RequestError as e:
        logger.error("LLM request failed (json path): %s", type(e).__name__, exc_info=True)
        raise RuntimeError(
            f"Сетевая ошибка при вызове LLM: {e}" + _proxy_auth_hint_message(e)
        ) from e

    if response.is_success:
        used_json_mode = True
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error("LLM response body is not JSON")
            raise RuntimeError("Ответ API не является JSON") from e
        if not isinstance(data, dict):
            raise RuntimeError("Ответ API: ожидался JSON-объект chat completion")
        raw, finish_reason = _assistant_message_text_with_finish(data, context="json mode")
    elif _json_mode_probably_unsupported(response.status_code, response.text or ""):
        logger.warning(
            "LLM json_object mode rejected (status=%s); retrying without response_format",
            response.status_code,
        )
    else:
        detail = _redact_secrets((response.text or "")[:1200])
        logger.error(
            "LLM HTTP error (json mode): status=%s model=%s body=%s",
            response.status_code,
            model,
            detail,
        )
        raise RuntimeError(_human_http_error(response))

    if raw is None:
        payload_plain: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            response = _post_chat(payload=payload_plain, timeout_sec=timeout_sec)
        except httpx.RequestError as e:
            logger.error("LLM request failed (plain path): %s", type(e).__name__, exc_info=True)
            raise RuntimeError(
                f"Сетевая ошибка при вызове LLM: {e}" + _proxy_auth_hint_message(e)
            ) from e

        if not response.is_success:
            detail = _redact_secrets((response.text or "")[:1200])
            logger.error(
                "LLM HTTP error (plain): status=%s model=%s body=%s",
                response.status_code,
                model,
                detail,
            )
            raise RuntimeError(_human_http_error(response))
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error("LLM response is not JSON (plain)")
            raise RuntimeError("Ответ API не является JSON") from e
        if not isinstance(data, dict):
            raise RuntimeError("Ответ API: ожидался JSON-объект chat completion")
        raw, finish_reason = _assistant_message_text_with_finish(data, context="plain")

    return raw, finish_reason, used_json_mode


def chat_completion_json(
    *,
    system: str,
    user: str,
    temperature: float = 0.3,
    timeout_sec: float | None = None,
) -> dict[str, Any]:
    """
    Chat completions с приоритетом response_format=json_object; при отказе API — без режима
    и разбор JSON из текста ответа. При обрезке ответа (length / «Unterminated string») — повтор с большим max_tokens.
    """
    t_out = timeout_sec if timeout_sec is not None else _timeout_sec()
    model = _model()
    budgets = _token_retry_budgets(_max_output_tokens())

    for attempt_idx, max_tok in enumerate(budgets):
        raw, finish_reason, used_json_mode = _request_llm_analysis_raw_string(
            system=system,
            user=user,
            temperature=temperature,
            timeout_sec=t_out,
            model=model,
            max_tokens=max_tok,
        )
        if finish_reason == "length":
            logger.warning(
                "LLM finish_reason=length (вывод мог быть обрезан по лимиту токенов), max_tokens=%s",
                max_tok,
            )
        try:
            parsed = _parse_json_object(raw)
            return _normalize_llm_analysis_json(parsed)
        except json.JSONDecodeError as e:
            truncated = finish_reason == "length" or _looks_like_truncated_json_error(e)
            if truncated and attempt_idx + 1 < len(budgets):
                logger.warning(
                    "LLM: ошибка разбора JSON (%s), повтор запроса с max_tokens=%s",
                    e.msg,
                    budgets[attempt_idx + 1],
                )
                continue
            snippet = _redact_secrets((raw or "")[:2000])
            logger.error(
                "LLM JSON parse failed: json_mode=%s err=%s snippet=%s",
                used_json_mode,
                e.msg,
                snippet,
            )
            raise RuntimeError(
                f"Модель вернула невалидный JSON: {e.msg}. "
                "Если сообщение про незакрытую строку или обрезку — задайте в `.env` больший "
                "`LLM_MAX_OUTPUT_TOKENS` (сейчас лимит повышается автоматически только в пределах нескольких попыток)."
            ) from e

    raise RuntimeError("Не удалось разобрать ответ LLM")  # pragma: no cover
