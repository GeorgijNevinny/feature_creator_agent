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
    cv_label = "time-series CV" if ohlcv else "k-fold CV"
    return [
        ("Подготовка моделей и разбиения данных…", "dim"),
        (f"Обучение baseline и сравнение метрик ({cv_label})…", ""),
        ("Проверка кандидатов признаков на нескольких моделях…", ""),
        ("Отбор успешных комбинаций и формирование отчёта…", "ok"),
    ]


def build_stages(profile: dict[str, Any]) -> list[AgentStage]:
    names = _profile_col_names(profile)
    ohlcv = _is_ohlcv_profile(names)

    analyst_msgs: list[tuple[str, str]] = [
        ("Анализ структуры и качества данных…", "dim"),
        ("Контекст для feature engineering готов.", "ok"),
    ]

    engineer_msgs: list[tuple[str, str]] = [
        ("Генерация и отбор кандидатов признаков…", "dim"),
        ("Проверка формул на утечку целевой переменной…", ""),
        (
            "Часть кандидатов отфильтрована (дубли / слабая информативность).",
            "warn",
        ),
        ("Пакет признаков готов к валидации.", "ok"),
    ]

    return [
        AgentStage(
            agent_id="analyst",
            title="Data Analyst Agent",
            messages=analyst_msgs,
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
