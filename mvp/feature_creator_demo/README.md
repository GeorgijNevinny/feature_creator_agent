# Feature Creator — демо для презентации

Визуально совпадает с `feature_creator_agent`, но **без LLM и без обучения моделей**. Показывает имитацию работы трёх агентов:

1. **Data Analyst Agent** — анализ схемы и ролей столбцов  
2. **Feature Engineering Agent** — генерация признаков  
3. **ML Validation Agent** — «тесты» на LightGBM, XGBoost, MLP  

## Запуск

```bash
cd feature_creator_demo
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Сценарий презентации

1. Загрузите CSV (позже — подготовленный датасет).  
2. Нажмите **«Запустить агентов»** — ~25–40 с (или быстрее с «Ускоренная демонстрация»).  
3. Вкладки **Агенты** (лог) и **Результат** (признаки + метрики).

### Сценарий Tesla (`eda/tesla.csv`)

В репозитории уже лежит `data/presentation_bundle.json` под файл **`tesla.csv`**:

1. Запустите демо: `streamlit run app.py`
2. Загрузите `eda/tesla.csv`
3. Нажмите **«Запустить агентов»** — агенты покажут 5 проверенных OHLCV-признаков и метрики CV

Перепроверка признаков офлайн:

```bash
pip install pandas scikit-learn
python scripts/validate_tesla_features.py
```

### Свой датасет

```bash
cp data/presentation_bundle.json.example data/presentation_bundle.json
```

- `match_filenames` — имена файлов, для которых подставляется этот JSON (пустой список = любой файл).  
- Заполните `feature_ideas`, `ml_validation`, `column_roles` так, как нужно на слайдах.

Без `presentation_bundle.json` результаты **генерируются эвристически** по именам столбцов в профиле CSV.

## Отличия от боевого MVP

| | `feature_creator_agent` | `feature_creator_demo` |
|--|-------------------------|-------------------------|
| LLM | да | нет |
| Обучение ML | нет | нет (имитация метрик) |
| Согласие на внешний API | да | не требуется |
