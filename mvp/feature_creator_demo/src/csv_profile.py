"""Чтение CSV из байтов и компактное профилирование для LLM."""

from __future__ import annotations

import csv
import io
import json
import math
import os
from typing import Any

import pandas as pd

DEFAULT_MAX_MB = 15.0
DEFAULT_PROFILE_MAX_ROWS = 50_000
ENCODINGS = ("utf-8", "utf-8-sig", "cp1251", "latin-1")
_SNIFF_CHUNK = 524_288
_DEFAULT_SEP_ORDER = (",", ";", "\t", "|")

# Короткие сэмплы и агрегаты — не полные «сырые» строки таблицы
_MAX_SAMPLE_STR_LEN = 64
_MAX_CATEGORY_LABEL_LEN = 48
_SAMPLE_VALUES_MIN = 3
_SAMPLE_VALUES_MAX = 5
_TOP_CATEGORIES_K = 8
_MAX_N_UNIQUE_FOR_TOP_CATEGORIES = 50
_BINARY_SCAN_MAX_CELLS = 500
_IDENTIFIER_LIKE_UNIQUE_RATIO = 0.92


def max_upload_bytes() -> int:
    mb = float(os.getenv("CSV_MAX_MB", str(DEFAULT_MAX_MB)))
    return int(mb * 1024 * 1024)


def max_upload_mb() -> float:
    return float(os.getenv("CSV_MAX_MB", str(DEFAULT_MAX_MB)))


def profile_max_rows() -> int:
    v = int(float(os.getenv("CSV_PROFILE_MAX_ROWS", str(DEFAULT_PROFILE_MAX_ROWS))))
    return max(1, min(v, 5_000_000))


def profile_sample_mode() -> str:
    m = (os.getenv("CSV_PROFILE_SAMPLE_MODE", "first") or "first").strip().lower()
    return m if m in ("first", "random") else "first"


def profile_sample_seed() -> int:
    return int(float(os.getenv("CSV_PROFILE_SAMPLE_SEED", "42")))


def detect_csv_separator(sample_text: str) -> str:
    """Простая эвристика: первая непустая строка, разделитель с максимальным числом полей."""
    line = ""
    for L in sample_text.splitlines():
        t = L.strip()
        if t:
            line = t
            break
    if not line:
        return ","
    best_sep = ","
    best_cols = 0
    for sep in _DEFAULT_SEP_ORDER:
        n_parts = len(line.split(sep))
        if n_parts > best_cols:
            best_cols = n_parts
            best_sep = sep
    if best_cols < 2:
        return ","
    return best_sep


def _separator_display(sep: str) -> str:
    return {
        ",": "запятая (,)",
        ";": "точка с запятой (;)",
        "\t": "табуляция",
        "|": "вертикальная черта (|)",
    }.get(sep, repr(sep))


def read_csv_bytes(raw: bytes, sep: str | None = None) -> tuple[pd.DataFrame, str, str]:
    """
    Читает CSV из байтов.

    Args:
        raw: содержимое файла.
        sep: разделитель полей; ``None`` — автоопределение по первым строкам для каждой кодировки.

    Returns:
        ``(dataframe, encoding, separator_description)`` — описание разделителя для UI.
    """
    if len(raw) == 0:
        raise ValueError("Файл пустой (0 байт). Загрузите непустой CSV.")

    if len(raw.strip()) == 0:
        raise ValueError("Файл содержит только пробельные символы. Загрузите CSV с данными.")

    head = raw[: min(len(raw), 8192)]
    if b"\x00" in head:
        raise ValueError(
            "Обнаружены нулевые байты: файл похож на двоичный, а не на текстовый CSV. "
            "Экспортируйте таблицу в текстовый CSV или выберите другой файл."
        )

    last_err: Exception | None = None
    for enc in ENCODINGS:
        try:
            sample = raw[:_SNIFF_CHUNK].decode(enc)
        except UnicodeDecodeError:
            continue

        if sep is not None:
            trial_seps = [sep]
        else:
            guessed = detect_csv_separator(sample)
            trial_seps = (guessed,) + tuple(s for s in _DEFAULT_SEP_ORDER if s != guessed)

        for s in trial_seps:
            try:
                df = pd.read_csv(
                    io.BytesIO(raw),
                    encoding=enc,
                    sep=s,
                    quoting=csv.QUOTE_MINIMAL,
                )
            except UnicodeDecodeError as e:
                last_err = e
                break
            except (pd.errors.ParserError, pd.errors.EmptyDataError) as e:
                last_err = e
                continue

            if df.shape[1] == 0:
                continue

            mode = "авто" if sep is None else "вручную"
            desc = f"{_separator_display(s)} · {mode}"
            return df, enc, desc

    detail = f" Последняя ошибка: {last_err}" if last_err else ""
    raise ValueError(
        "Не удалось прочитать файл как CSV: ни одна пара «кодировка + разделитель» не подошла."
        + detail
        + " Проверьте разделитель в боковой панели или что файл действительно текстовый CSV."
    )


def _binary_cell_to_str(value: Any) -> str:
    if isinstance(value, memoryview):
        value = bytes(value)
    if isinstance(value, bytearray):
        value = bytes(value)
    if not isinstance(value, bytes):
        return str(value)
    if len(value) > 1024:
        return f"<binary omitted {len(value)} bytes>"
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return f"<binary {len(value)} bytes>"


def _series_has_binary(series: pd.Series) -> bool:
    seen = 0
    for v in series:
        if pd.isna(v):
            continue
        if isinstance(v, (bytes, bytearray, memoryview)):
            return True
        seen += 1
        if seen >= _BINARY_SCAN_MAX_CELLS:
            break
    return False


def prepare_for_profile(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Копия датасета для профилирования: бинарные ячейки → строки, лимит строк (первые N или случайная выборка).
    Второй элемент — метаданные для UI и JSON-профиля.
    """
    n_total = len(df)
    out = df.copy()
    binary_columns: list[str] = []

    for col in out.columns:
        s = out[col]
        if _series_has_binary(s):
            out[col] = s.map(lambda x: _binary_cell_to_str(x) if pd.notna(x) else x)
            binary_columns.append(str(col))

    cap = profile_max_rows()
    mode = profile_sample_mode()
    if n_total <= cap:
        subset = out
        sampling = {
            "capped": False,
            "rows_used": n_total,
            "row_limit": cap,
            "mode": mode,
        }
    else:
        if mode == "random":
            seed = profile_sample_seed()
            subset = out.sample(n=cap, random_state=seed, replace=False)
            sampling = {
                "capped": True,
                "rows_used": cap,
                "row_limit": cap,
                "mode": "random",
                "sample_seed": seed,
            }
        else:
            subset = out.head(cap)
            sampling = {
                "capped": True,
                "rows_used": cap,
                "row_limit": cap,
                "mode": "first",
            }

    meta: dict[str, Any] = {
        "source_total_rows": n_total,
        "binary_columns_normalized": binary_columns,
        "profile_sampling": sampling,
    }
    return subset, meta


def _truncate_str(value: Any, max_len: int = _MAX_SAMPLE_STR_LEN) -> str:
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = _binary_cell_to_str(value)
    s = str(value).replace("\n", " ").replace("\r", " ")
    s = s.strip()
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def _safe_sample_values(series: pd.Series, k: int = 4) -> list[str]:
    """3–5 коротких примеров: первые встретившиеся уникальные ненулевые значения (порядок обхода)."""
    k = max(_SAMPLE_VALUES_MIN, min(k, _SAMPLE_VALUES_MAX))
    seen: set[str] = set()
    out: list[str] = []
    for v in series:
        if pd.isna(v) or (isinstance(v, float) and math.isnan(v)):
            continue
        t = _truncate_str(v, _MAX_SAMPLE_STR_LEN)
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= k:
            break
    return out


def _round_num(x: float) -> float | None:
    if math.isnan(x) or math.isinf(x):
        return None
    ax = abs(x)
    if ax >= 1e6 or (ax > 0 and ax < 1e-4):
        return float(f"{x:.6g}")
    return round(float(x), 6)


def _numeric_min_mean_max(series: pd.Series, n: int, n_unique: int) -> dict[str, float] | None:
    if n_unique == 0:
        return None
    if n > 5 and n_unique >= max(2, int(n * _IDENTIFIER_LIKE_UNIQUE_RATIO)):
        return None
    num = pd.to_numeric(series, errors="coerce")
    valid = num.dropna()
    if valid.empty:
        return None
    mn = float(valid.min())
    mx = float(valid.max())
    mean = float(valid.mean())
    raw = {"min": _round_num(mn), "mean": _round_num(mean), "max": _round_num(mx)}
    out = {k: v for k, v in raw.items() if v is not None}
    if not out:
        return None
    return out


def _top_categories(series: pd.Series, n_rows: int) -> list[dict[str, Any]] | None:
    if n_rows == 0 or series.isna().all():
        return None
    if series.nunique(dropna=True) > _MAX_N_UNIQUE_FOR_TOP_CATEGORIES:
        return None

    vc = series.astype("object").value_counts(dropna=True, normalize=False)
    if vc.empty:
        return None
    top = vc.head(_TOP_CATEGORIES_K)
    if int(vc.sum()) == 0:
        return None

    out: list[dict[str, Any]] = []
    for val, cnt in top.items():
        label = _truncate_str(val, _MAX_CATEGORY_LABEL_LEN)
        share = float(cnt) / float(n_rows) if n_rows else 0.0
        out.append({"value": label, "share": round(share, 4)})
    return out


def _should_offer_top_categories(series: pd.Series, n_unique: int) -> bool:
    if n_unique == 0 or n_unique > _MAX_N_UNIQUE_FOR_TOP_CATEGORIES:
        return False
    if pd.api.types.is_bool_dtype(series):
        return True
    if isinstance(series.dtype, pd.CategoricalDtype):
        return True
    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        return True
    if pd.api.types.is_integer_dtype(series) and n_unique <= 40:
        return True
    return False


def _datetime_min_max(series: pd.Series) -> dict[str, str] | None:
    if not pd.api.types.is_datetime64_any_dtype(series):
        return None
    clean = series.dropna()
    if clean.empty:
        return None
    mn = clean.min()
    mx = clean.max()
    return {
        "min": _truncate_str(pd.Timestamp(mn).isoformat(), 32),
        "max": _truncate_str(pd.Timestamp(mx).isoformat(), 32),
    }


def _columns_payload(work: pd.DataFrame, n: int, max_columns: int) -> tuple[list[dict[str, Any]], bool, int]:
    truncated = work.shape[1] > max_columns
    use = work.iloc[:, :max_columns] if truncated else work
    n_cols = int(use.shape[1])
    columns: list[dict[str, Any]] = []
    for col in use.columns:
        s = use[col]
        name = str(col)
        dtype = str(s.dtype)
        null_count = int(s.isna().sum())
        missing_pct = round(100.0 * null_count / n if n else 0.0, 2)
        n_unique = int(s.nunique(dropna=True))

        entry: dict[str, Any] = {
            "name": name,
            "dtype": dtype,
            "missing_pct": missing_pct,
            "n_unique": n_unique,
            "sample_values": _safe_sample_values(s, k=4),
        }

        dt_range = _datetime_min_max(s)
        if dt_range is not None:
            entry["datetime_range"] = dt_range

        if pd.api.types.is_bool_dtype(s):
            tc = _top_categories(s, n)
            if tc is not None:
                entry["top_categories"] = tc
        elif _should_offer_top_categories(s, n_unique):
            tc = _top_categories(s, n)
            if tc is not None:
                entry["top_categories"] = tc

        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            stats = _numeric_min_mean_max(s, n, n_unique)
            if stats is not None:
                entry["numeric_stats"] = stats
        elif entry.get("numeric_stats") is None and (
            pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)
        ):
            stats = _numeric_min_mean_max(s, n, n_unique)
            if stats is not None:
                entry["numeric_stats"] = stats

        columns.append(entry)
    return columns, truncated, n_cols


def build_dataset_profile_bundle(
    df: pd.DataFrame, max_columns: int = 200
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, Any]]:
    """
    Один проход: подготовка строк/бинарных колонок + словарь профиля + подготовленный срез для UI.
    """
    prepared, prep_meta = prepare_for_profile(df)
    n = len(prepared)
    columns, truncated_cols, n_cols = _columns_payload(prepared, n, max_columns)

    profile: dict[str, Any] = {
        "source_total_rows": prep_meta["source_total_rows"],
        "n_rows": n,
        "n_cols": n_cols,
        "truncated_to_first_columns": truncated_cols,
        "profile_sampling": prep_meta["profile_sampling"],
        "binary_columns_normalized": prep_meta["binary_columns_normalized"],
        "columns": columns,
    }
    return profile, prepared, prep_meta


def build_dataset_profile(df: pd.DataFrame, max_columns: int = 200) -> dict[str, Any]:
    """Компактный JSON-подобный словарь (с лимитом строк и нормализацией бинарных колонок)."""
    profile, _prepared, _meta = build_dataset_profile_bundle(df, max_columns=max_columns)
    return profile


def column_profile_table(df: pd.DataFrame) -> pd.DataFrame:
    """Таблица для UI: типы, non-null, пропуски, уникальность."""
    return pd.DataFrame(
        {
            "dtype": df.dtypes.astype(str),
            "non_null": df.count(),
            "null_count": df.isna().sum(),
            "n_unique": df.nunique(dropna=True),
        }
    )


def build_dataset_summary_json(df: pd.DataFrame, max_columns: int = 200) -> str:
    """Сериализация профиля для отправки в LLM."""
    profile = build_dataset_profile(df, max_columns=max_columns)
    return json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
