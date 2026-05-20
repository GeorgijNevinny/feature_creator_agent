"""Имитация работы трёх AI-агентов (без реальных API и обучения)."""

from __future__ import annotations

import html
import random
import time
from dataclasses import dataclass, field
from typing import Any

# Доли длительности этапов (сумма = 1); валидация — самая долгая
_STAGE_DURATION_SHARE = {
    "analyst": 0.20,
    "engineer": 0.25,
    "validator": 0.55,
}

# Обычный режим: ~3 мин ± 20 с; быстрый: ~55 с ± 8 с
_PIPELINE_DURATION_NORMAL = (160.0, 200.0)
_PIPELINE_DURATION_FAST = (47.0, 63.0)

_OHLCV_TOP_FEATURES = (
    "gap_from_prev_close_pct",
    "vwap_proxy_dev",
    "volatility_20d",
    "intraday_range_pct",
    "volume_zscore_20",
)


@dataclass
class AgentStage:
    agent_id: str
    title: str
    messages: list[tuple[str, str]] = field(default_factory=list)


def _profile_col_names(profile: dict[str, Any]) -> list[str]:
    return [str(c.get("name", "")) for c in (profile.get("columns") or []) if c.get("name")]


def _norm_col(name: str) -> str:
    return name.lower().replace(" ", "_")


def _is_ohlcv_profile(names: list[str]) -> bool:
    nn = {_norm_col(n) for n in names}
    return "close" in nn and ("date" in nn or "timestamp" in nn)


def _pipeline_target_seconds(fast_mode: bool) -> float:
    lo, hi = _PIPELINE_DURATION_FAST if fast_mode else _PIPELINE_DURATION_NORMAL
    return random.uniform(lo, hi)


def _distribute_duration(n_steps: int, total_seconds: float) -> list[float]:
    """Случайные паузы между шагами; сумма равна total_seconds."""
    if n_steps <= 0:
        return []
    if n_steps == 1:
        return [total_seconds]
    weights = [random.uniform(0.45, 1.0) for _ in range(n_steps)]
    scale = total_seconds / sum(weights)
    return [w * scale for w in weights]


def _validator_messages(ohlcv: bool) -> list[tuple[str, str]]:
    features = list(_OHLCV_TOP_FEATURES) if ohlcv else [
        "candidate_feature_1",
        "candidate_feature_2",
        "candidate_feature_3",
        "candidate_feature_4",
        "candidate_feature_5",
    ]
    models = ("LightGBM", "XGBoost", "MLP (PyTorch)")

    msgs: list[tuple[str, str]] = [
        ("Инициализация пайплайна: LightGBM, XGBoost, MLP…", ""),
        ("Подготовка препроцессинга и разбиения 5-fold CV…", ""),
        ("Baseline без новых признаков — обучение по фолдам…", ""),
        ("Baseline: агрегация ROC-AUC…", ""),
    ]
    for i, feat in enumerate(features, 1):
        msgs.append((f"Признак {i}/{len(features)}: {feat} — запуск CV…", ""))
        for model in models:
            msgs.append((f"  · {model}: fit / predict по фолдам…", ""))
        msgs.append((f"  · сравнение с baseline, Δ ROC-AUC…", "ok" if i <= 3 else ""))
    msgs.extend(
        [
            ("Сводная таблица: признак × модель × метрика…", ""),
            ("Отбор комбинаций со статусом passed…", ""),
            ("Формирование превью обогащённых строк…", ""),
            ("Итоговый отчёт сформирован.", "ok"),
        ]
    )
    return msgs


def build_stages(profile: dict[str, Any]) -> list[AgentStage]:
    names = _profile_col_names(profile)
    n_rows = profile.get("n_rows", "?")
    n_cols = profile.get("n_cols", len(names))
    sample_cols = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
    ohlcv = _is_ohlcv_profile(names)

    analyst_tail = (
        "Гипотеза задачи: next-day direction (OHLCV) + time-series CV",
        "ok",
    ) if ohlcv else (
        "Гипотеза задачи: classification + tabular baseline",
        "ok",
    )

    engineer_msgs: list[tuple[str, str]] = [
        ("Получен контекст от Data Analyst Agent.", "dim"),
    ]
    if ohlcv:
        engineer_msgs.extend(
            [
                (
                    "Кандидаты: gap overnight, typical-price deviation, "
                    "rolling volatility, intraday range, volume z-score…",
                    "",
                ),
                ("Сортировка по date; лаги только по прошлым дням…", ""),
                ("Проверка формул на утечку target…", ""),
                ("Отброшены дублирующие признаки (overnight ≡ gap).", "warn"),
                ("Топ-5 признаков отобраны по Δ ROC-AUC на 5-fold TSCV.", "ok"),
            ]
        )
    else:
        engineer_msgs.extend(
            [
                ("Поиск кандидатов: log-трансформы, target encoding, рекенси…", ""),
                ("Проверка формул на утечку target…", ""),
                ("Отбрасываны 2 идеи с высокой корреляцией с id.", "warn"),
                ("Ранжирование кандидатов по информативности…", ""),
            ]
        )
    engineer_msgs.extend(
        [
            ("Пакет признаков готов к валидации.", "ok"),
            ("Передача в ML Validation Agent.", "dim"),
        ]
    )

    return [
        AgentStage(
            agent_id="analyst",
            title="Data Analyst Agent",
            messages=[
                ("Загрузка профиля датасета…", "dim"),
                (f"Строк в профиле: {n_rows} · столбцов: {n_cols}", ""),
                (f"Сканирование полей: {sample_cols or '—'}", ""),
                ("Оценка пропусков и кардинальности…", ""),
                ("Классификация ролей: id / timestamp / target / feature…", ""),
                analyst_tail,
                ("Отчёт передан Feature Engineering Agent.", "ok"),
            ],
        ),
        AgentStage(
            agent_id="engineer",
            title="Feature Engineering Agent",
            messages=engineer_msgs,
        ),
        AgentStage(
            agent_id="validator",
            title="ML Validation Agent",
            messages=_validator_messages(ohlcv),
        ),
    ]


_CARD_META = [
    ("analyst", "📊", "Data Analyst", "Анализ данных"),
    ("engineer", "⚙️", "Feature Engineer", "Feature engineering"),
    ("validator", "🧪", "ML Validator", "Тест на моделях"),
]

_STATUS_LABEL = {"pending": "Ожидание", "running": "В работе…", "done": "Готово"}


def agent_cards_markup(states: dict[str, str]) -> str:
    parts = ['<div class="agent-pipeline">']
    for aid, icon, name, sub in _CARD_META:
        stt = states.get(aid, "pending")
        label = _STATUS_LABEL.get(stt, stt)
        parts.append(
            f'<div class="agent-card {stt}">'
            f'<div class="agent-card-head">'
            f'<div class="agent-icon">{icon}</div>'
            f"<div><div class='agent-name'>{html.escape(name)}</div>"
            f"<div class='agent-status'>{html.escape(label)} · {html.escape(sub)}</div>"
            f"</div></div></div>"
        )
    parts.append("</div>")
    return "".join(parts)


def log_html(lines: list[tuple[str, str]]) -> str:
    rows = []
    for text, css in lines:
        cls = f"agent-log-line {css}".strip()
        rows.append(f'<div class="{cls}">{html.escape(text)}</div>')
    return f'<div class="agent-log">{"".join(rows)}</div>'


def run_agent_pipeline(
    profile: dict[str, Any],
    *,
    cards_placeholder: Any,
    log_placeholder: Any,
    progress_bar: Any,
    fast_mode: bool = False,
) -> str:
    stages = build_stages(profile)
    total_seconds = _pipeline_target_seconds(fast_mode)
    total_steps = sum(len(s.messages) for s in stages)

    log_lines: list[tuple[str, str]] = []
    states = {aid: "pending" for aid, *_ in _CARD_META}

    cards_placeholder.markdown(agent_cards_markup(states), unsafe_allow_html=True)
    log_placeholder.markdown(log_html(log_lines), unsafe_allow_html=True)

    step = 0

    for stage in stages:
        stage_budget = total_seconds * _STAGE_DURATION_SHARE.get(stage.agent_id, 0.33)
        delays = _distribute_duration(len(stage.messages), stage_budget)

        for aid, *_ in _CARD_META:
            if aid == stage.agent_id:
                states[aid] = "running"
            elif states[aid] == "running":
                states[aid] = "done"
        cards_placeholder.markdown(agent_cards_markup(states), unsafe_allow_html=True)

        for (text, css), delay in zip(stage.messages, delays, strict=True):
            log_lines.append((f"[{stage.title}] {text}", css))
            log_placeholder.markdown(log_html(log_lines), unsafe_allow_html=True)
            time.sleep(delay)
            step += 1
            progress_bar.progress(min(1.0, step / max(total_steps, 1)))

        states[stage.agent_id] = "done"
        cards_placeholder.markdown(agent_cards_markup(states), unsafe_allow_html=True)

    progress_bar.progress(1.0)
    return log_html(log_lines)
