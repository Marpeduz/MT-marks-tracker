# MT-marks-tracker

Web service for tracking marks in the World of Tanks (RU — Lesta).

## Data pipeline

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests

python scripts/update.py marks     # планки + история (по умолчанию)
python scripts/update.py vehicles  # редкое обновление справочника техники
python scripts/update.py icons     # пересборка спрайта иконок
python scripts/build_css.py        # сборка Tailwind в assets/app.css
```

CSS собирается standalone CLI без Node.js; бинарник кэшируется в `.cache/tailwind/`.

Иконки танков собраны в `assets/icons.svg` и подключаются одним запросом. При скролле таблицы сетевых запросов нет.

`data/vehicles.json` — статический справочник. Контур `marks` читает его с диска и не зависит от доступности API метаданных. Если файл отсутствует, он создаётся из API автоматически.

Снимок публикуется только после валидации. Запись идёт через временный файл и `os.replace`, поэтому `latest.json` никогда не остаётся битым. Предупреждения валидации пишутся в `data/meta.json`.

Подробности: `docs/ARCHITECTURE.md`.
