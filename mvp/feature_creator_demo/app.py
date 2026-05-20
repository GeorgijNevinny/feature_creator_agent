"""
Feature creator: загрузка CSV, цепочка AI-агентов, feature engineering и ML-валидация.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

from src.agents_sim import agent_cards_markup, run_agent_pipeline
from src.csv_profile import (
    build_dataset_profile_bundle,
    max_upload_bytes,
    max_upload_mb,
    read_csv_bytes,
)
from src.results_builder import build_demo_results
from src.theme import inject_theme

_SUMMARY_LABELS = {
    "domain": "Предметная область",
    "what_is_measured": "Что измеряется",
    "possible_ml_task_types": "Типы ML-задач",
    "possible_ml_task_comment": "Комментарий к задаче",
    "uncertainty_note": "Заметки по интерпретации",
}


def _section_heading(text: str, *, spaced: bool = False) -> None:
    extra = " section-heading--spaced" if spaced else ""
    st.markdown(
        f'<p class="section-heading{extra}">{html.escape(text)}</p>',
        unsafe_allow_html=True,
    )


def _app_header(max_mb: float) -> None:
    st.markdown(
        f"""
<div class="app-header">
  <h1 class="app-page-title">Feature Creator</h1>
  <p class="app-page-subtitle">
    Загрузите CSV до {max_mb:g}&nbsp;МБ — три AI-агента проанализируют данные,
    предложат признаки и проверят их на табличных и нейросетевых моделях.
  </p>
</div>
        """,
        unsafe_allow_html=True,
    )


def _file_meta_bar(filename: str, n_rows: int, n_cols: int) -> None:
    rows_label = f"{n_rows:,}".replace(",", "\u202f")
    st.markdown(
        f"""
<div class="file-meta-bar">
  <span class="file-meta-chip">{html.escape(filename)}</span>
  <span class="file-meta-chip">{rows_label} строк</span>
  <span class="file-meta-chip">{n_cols} столбцов</span>
</div>
        """,
        unsafe_allow_html=True,
    )


def _render_dataset_summary(ds: dict) -> None:
    _section_heading("Сводка по датасету")
    cards: list[str] = []
    for key, label in _SUMMARY_LABELS.items():
        if key == "uncertainty_note":
            continue
        val = ds.get(key)
        if val is None or val == "":
            continue
        text = ", ".join(str(v) for v in val) if isinstance(val, list) else str(val)
        cards.append(
            f'<div class="summary-card"><h4>{html.escape(label)}</h4>'
            f"<p>{html.escape(text)}</p></div>"
        )
    if cards:
        st.markdown(
            f'<div class="summary-grid">{"".join(cards)}</div>',
            unsafe_allow_html=True,
        )


def _render_results(result: dict) -> None:
    ds = result.get("dataset_summary")
    if isinstance(ds, dict) and ds:
        _render_dataset_summary(ds)

    cr = result.get("column_roles")
    if isinstance(cr, list) and cr:
        _section_heading("Роли столбцов")
        st.dataframe(pd.DataFrame(cr), width="stretch", hide_index=True)

    fi = result.get("feature_ideas")
    if isinstance(fi, list) and fi:
        _section_heading("Сгенерированные признаки")
        st.dataframe(pd.DataFrame(fi), width="stretch", hide_index=True)

    ml = result.get("ml_validation")
    if isinstance(ml, list) and ml:
        _section_heading("Валидация на моделях")
        st.caption(
            "Статус **passed** — устойчивый прирост метрики на k-fold кросс-валидации."
        )
        st.dataframe(pd.DataFrame(ml), width="stretch", hide_index=True)
        passed = sum(1 for r in ml if r.get("status") == "passed")
        st.markdown(
            f'<p style="text-align:center;margin:0.75rem 0 0;">'
            f'<span class="metric-pill">{passed} комбинаций признак×модель прошли отбор</span></p>',
            unsafe_allow_html=True,
        )

    preview = result.get("enriched_preview")
    if isinstance(preview, list) and preview:
        _section_heading("Превью обогащённых данных")
        st.dataframe(pd.DataFrame(preview), width="stretch", hide_index=True)

    with st.expander("Экспорт JSON", expanded=False):
        st.json({k: v for k, v in result.items() if k != "_meta"})


def _render_results_page(result: dict) -> None:
    _section_heading("Результаты", spaced=True)
    _render_results(result)
    _, dl_col, _ = st.columns([1, 2, 1])
    with dl_col:
        st.download_button(
            "Скачать отчёт (JSON)",
            data=json.dumps(
                {k: v for k, v in result.items() if k != "_meta"},
                ensure_ascii=False,
                indent=2,
            ),
            file_name="feature_creator_report.json",
            mime="application/json",
            use_container_width=True,
        )


def main() -> None:
    max_bytes = max_upload_bytes()
    max_mb = max_upload_mb()

    st.set_page_config(page_title="Feature Creator", layout="centered")
    inject_theme()

    with st.sidebar:
        st.header("Настройки")
        sep_choice = st.selectbox(
            "Разделитель полей",
            options=["auto", ",", ";", "\t", "|"],
            format_func=lambda x: {
                "auto": "Авто",
                ",": "Запятая (,)",
                ";": "Точка с запятой (;)",
                "\t": "Табуляция",
                "|": "Вертикальная черта (|)",
            }[x],
            help="При «Авто» разделитель определяется по первой непустой строке.",
            key="csv_sep_choice",
        )
        st.checkbox(
            "Быстрый режим",
            value=False,
            help="Сокращённый прогон (~1 мин вместо ~3 мин).",
            key="fast_pipeline",
        )

    _app_header(max_mb)

    with st.container(border=True):
        uploaded = st.file_uploader(
            "CSV",
            type=["csv"],
            help="Текстовый файл в формате CSV.",
            label_visibility="collapsed",
        )
        if not uploaded:
            st.markdown(
                '<p class="upload-hint-card">Выберите CSV-файл, чтобы запустить агентов.</p>',
                unsafe_allow_html=True,
            )

    if not uploaded:
        return

    raw = uploaded.getvalue()
    if len(raw) == 0 or len(raw.strip()) == 0:
        st.error("Файл пустой. Загрузите непустой CSV.")
        return
    if len(raw) > max_bytes:
        st.error(f"Файл больше лимита {max_mb:g} МБ.")
        return

    sep_arg = None if sep_choice == "auto" else sep_choice
    try:
        df, _, _ = read_csv_bytes(raw, sep=sep_arg)
    except ValueError as e:
        st.error(str(e))
        return
    except Exception as e:
        st.error(f"Ошибка чтения: {e}")
        return

    fname = uploaded.name or "upload.csv"
    fast_mode = st.session_state.get("fast_pipeline", False)

    _file_meta_bar(fname, len(df), df.shape[1])

    with st.container(border=True):
        _section_heading("Исходные данные")
        st.dataframe(df.head(10), width="stretch", hide_index=True)

    _, btn_col, _ = st.columns([1, 1, 1], gap="medium")
    with btn_col:
        run_clicked = st.button(
            "Запустить агентов",
            type="primary",
            use_container_width=True,
            help="Анализ данных → генерация признаков → кросс-валидация на моделях.",
        )

    upload_key = f"{fname}:{len(raw)}:{sep_choice}"
    if st.session_state.get("_upload_key") != upload_key:
        st.session_state["_upload_key"] = upload_key
        st.session_state.pop("pipeline_result", None)
        st.session_state.pop("pipeline_log_html", None)

    profile, _, _ = build_dataset_profile_bundle(df)
    result = st.session_state.get("pipeline_result")
    done_states = {"analyst": "done", "engineer": "done", "validator": "done"}

    if run_clicked:
        _section_heading("Пайплайн агентов", spaced=True)
        cards_ph = st.empty()
        log_ph = st.empty()
        progress = st.progress(0.0)
        final_log = run_agent_pipeline(
            profile,
            cards_placeholder=cards_ph,
            log_placeholder=log_ph,
            progress_bar=progress,
            fast_mode=fast_mode,
        )
        progress.empty()
        result = build_demo_results(
            profile=profile,
            df=df,
            upload_filename=fname,
        )
        st.session_state["pipeline_log_html"] = final_log
        st.session_state["pipeline_result"] = result
        _render_results_page(result)
    elif result:
        _section_heading("Пайплайн агентов", spaced=True)
        st.markdown(agent_cards_markup(done_states), unsafe_allow_html=True)
        if st.session_state.get("pipeline_log_html"):
            st.markdown(st.session_state["pipeline_log_html"], unsafe_allow_html=True)
        _render_results_page(result)
    else:
        st.info("Нажмите **«Запустить агентов»** — анализ и результаты появятся ниже.")


if __name__ == "__main__":
    main()
