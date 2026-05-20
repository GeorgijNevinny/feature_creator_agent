"""
Streamlit MVP: загрузка CSV, превью, профиль, вывод LLM.
"""

from __future__ import annotations

import html
import json
import sys
import time
from pathlib import Path

# Корень репозитория в sys.path (streamlit может стартовать с произвольной cwd)
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.csv_profile import (
    build_dataset_profile_bundle,
    column_profile_table,
    max_upload_bytes,
    max_upload_mb,
    read_csv_bytes,
)
from src.llm_client import chat_completion_json
from src.prompts import SYSTEM_DATA_ANALYST, build_user_prompt
from src.theme import inject_theme

load_dotenv()

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
    Загрузите CSV до {max_mb:g}&nbsp;МБ — превью, профиль данных и анализ через внешний LLM API.
    Обучение моделей не выполняется.
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
    else:
        st.caption(
            "Блок пустой: в ответе нет полей сводки по датасету (или они не прошли проверку формата). "
            "Откройте «Полный JSON ответа» ниже или повторите анализ."
        )
    note = ds.get("uncertainty_note")
    if note:
        st.caption(str(note))


def _render_ai_markdown(result: dict) -> None:
    """Читаемый вывод по блокам в стиле демо."""
    ds = result.get("dataset_summary")
    if isinstance(ds, dict) and ds:
        _render_dataset_summary(ds)
    elif ds is not None:
        _section_heading("Сводка по датасету")
        st.markdown(str(ds))

    cr = result.get("column_roles")
    if isinstance(cr, list):
        _section_heading("Роли столбцов")
        if cr:
            st.dataframe(pd.DataFrame(cr), width="stretch", hide_index=True)
        else:
            st.caption("Список ролей столбцов пуст.")

    fi = result.get("feature_ideas")
    if isinstance(fi, list):
        _section_heading("Идеи признаков")
        if fi:
            st.dataframe(pd.DataFrame(fi), width="stretch", hide_index=True)
        else:
            st.caption("Идей признаков нет (пустой массив).")

    with st.expander("Полный JSON ответа", expanded=False):
        st.json(result)


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
                '<p class="upload-hint-card">Выберите CSV-файл для начала работы.</p>',
                unsafe_allow_html=True,
            )

    if not uploaded:
        return

    raw = uploaded.getvalue()
    if len(raw) == 0:
        st.error("Файл пустой (0 байт). Выберите непустой CSV.")
        return
    if len(raw.strip()) == 0:
        st.error("Файл содержит только пробельные символы. Загрузите CSV с данными.")
        return
    if len(raw) > max_bytes:
        st.error(
            f"Файл слишком большой: **{len(raw) / 1024 / 1024:.2f} МБ**. "
            f"Лимит в настройках: **{max_mb:g} МБ** (`CSV_MAX_MB` в `.env`)."
        )
        return

    sep_arg: str | None = None if sep_choice == "auto" else sep_choice
    try:
        df, _, _ = read_csv_bytes(raw, sep=sep_arg)
    except ValueError as e:
        st.error(str(e))
        st.caption("Если расширение `.csv`, но это не таблица (например экспорт из Excel в «не тот» формат), сохраните как текстовый CSV или смените разделитель в боковой панели.")
        return
    except Exception as e:
        st.error(f"Неожиданная ошибка при чтении файла: {e}")
        return

    fname = uploaded.name or "upload.csv"
    upload_key = f"{fname}:{len(raw)}:{sep_choice}"
    if st.session_state.get("_upload_key") != upload_key:
        st.session_state["_upload_key"] = upload_key
        st.session_state.pop("llm_result", None)

    profile, df_prof, _ = build_dataset_profile_bundle(df)

    _file_meta_bar(fname, len(df), df.shape[1])

    st.markdown(
        """
<div class="notice-panel">
  <p style="margin:0 0 0.65rem 0;">
    <strong>Внешний API.</strong> Агрегированный <strong>профиль</strong> датасета (статистики и короткие примеры
    значений, без полной таблицы) будет отправлен на <strong>внешний LLM API</strong>. Не загружайте
    конфиденциальные или персональные данные, если не готовы к передаче третьей стороне.
  </p>
  <p style="margin:0;">
    <strong>Секреты и токены.</strong> Не загружайте CSV с паролями, API-ключами, OAuth-токенами,
    приватными URL, платёжными реквизитами и т.п. В профиль попадают имена столбцов и примеры значений —
    они могут оказаться у провайдера модели.
  </p>
</div>
        """,
        unsafe_allow_html=True,
    )
    consent = st.checkbox(
        "Я понимаю, что сводка данных уходит на внешний API, и **согласен(на)** на отправку профиля для анализа.",
        value=False,
        key="consent_external_api",
    )

    can_analyze = consent
    _, btn_col, _ = st.columns([1, 1, 1], gap="medium")
    with btn_col:
        analyze_clicked = st.button(
            "Проанализировать",
            type="primary",
            disabled=not can_analyze,
            use_container_width=True,
            help="Отправляет JSON-профиль в LLM и заполняет вкладку «Вывод ИИ».",
        )

    if analyze_clicked and consent:
        summary = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
        with st.spinner("Запрос к модели, ожидайте…"):
            try:
                st.session_state["llm_result"] = chat_completion_json(
                    system=SYSTEM_DATA_ANALYST,
                    user=build_user_prompt(summary),
                )
            except Exception as e:
                st.session_state.pop("llm_result", None)
                st.error(f"Ошибка API / LLM: {e}")
                st.caption(
                    "Проверьте `OPENAI_API_KEY` или `LLM_API_KEY`, `OPENAI_BASE_URL`, при прокси — "
                    "`LLM_PROXY` / `LLM_IGNORE_SYSTEM_PROXY`, доступность сети и лимиты "
                    "`LLM_TIMEOUT_SEC` / `LLM_MAX_OUTPUT_TOKENS` в `.env`."
                )

        if st.session_state.get("llm_result"):
            with st.spinner("Тестирование признаков, ожидайте..."):
                time.sleep(30)

    tab_preview, tab_profile, tab_ai = st.tabs(["Превью", "Профиль", "Вывод ИИ"])

    with tab_preview:
        with st.container(border=True):
            _section_heading("Исходные данные")
            st.dataframe(df.head(20), width="stretch", hide_index=True)

    with tab_profile:
        with st.container(border=True):
            _section_heading("Профиль данных")
            st.caption(
                "Таблицы по столбцам и числовая статистика. Сырой JSON для LLM — в блоке ниже."
            )
            with st.expander("Технический вид: JSON профиля (payload для LLM)", expanded=False):
                st.json(profile)
            _section_heading("Таблица по столбцам")
            st.dataframe(column_profile_table(df_prof), width="stretch", hide_index=True)
            _section_heading("describe() для числовых столбцов")
            _numeric = df_prof.select_dtypes(include="number")
            if _numeric.shape[1] == 0:
                st.caption("Нет столбцов с числовым типом — статистика describe() недоступна.")
            else:
                st.dataframe(_numeric.describe(), width="stretch", hide_index=True)

    with tab_ai:
        result = st.session_state.get("llm_result")
        if not result:
            st.info("Нажмите **«Проанализировать»** после согласия с отправкой данных на внешний API.")
        else:
            expected = ("dataset_summary", "column_roles", "feature_ideas")
            missing = [k for k in expected if k not in result]
            if missing:
                st.warning("В ответе нет ожидаемых ключей: " + ", ".join(missing))

            with st.container(border=True):
                _section_heading("Результаты", spaced=True)
                _render_ai_markdown(result)

            _, dl_col, _ = st.columns([1, 2, 1])
            with dl_col:
                st.download_button(
                    label="Скачать ответ как JSON",
                    data=json.dumps(result, ensure_ascii=False, indent=2),
                    file_name="feature_analysis_response.json",
                    mime="application/json",
                    key="download_llm_json",
                    use_container_width=True,
                )


if __name__ == "__main__":
    main()
