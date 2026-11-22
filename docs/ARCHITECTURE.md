# Архитектура MT-marks-tracker

## Принципы

1. Нулевая стоимость: GitHub Pages + GitHub Actions + статические JSON. Никакого сервера и БД.
2. Два независимых контура данных: статические метаданные техники и динамические планки. Падение одного не блокирует другой.
3. Публикация только валидного снимка: сначала собрать и проверить всё в памяти, потом атомарно заменить файлы.
4. Клиент делает всю работу по фильтрации и сортировке. Сервер отдаёт только данные.

## Структура репозитория

Деплой собирает каталог `_site`: туда попадают `index.html`, `assets/` и публичные файлы из `data/`. Служебные `vehicles.json`, `pipeline/`, `tests/` в артефакт не входят.

```
.
├─ .github/workflows/
│  ├─ sync-vehicles.yml       # метаданные: вручную или по расписанию при патчах
│  ├─ sync-marks.yml          # планки: 2 раза в день
│  └─ deploy.yml              # GitHub Pages
├─ data/
│  ├─ vehicles.json           # статический справочник: id, tag, nation, type, tier, role, флаги
│  ├─ latest.json             # публикуемый снимок: updated_at + vehicles[] с marks
│  ├─ meta.json               # версия, время, количество, статус источников
│  └─ history/{tank_id}.json  # дневные точки: date, 65, 85, 95, 100
├─ pipeline/
│  ├─ config.py               # URL, лимиты, пороги аномалий
│  ├─ sources.py              # HTTP с retry и таймаутами
│  ├─ models.py               # Pydantic-схемы
│  ├─ validate.py             # инварианты и отсечение аномалий
│  ├─ history.py              # атомарная запись истории
│  ├─ build.py                # сборка latest.json и meta.json
│  └─ main.py                 # оркестрация контуров и CLI
├─ scripts/
│  ├─ update.py               # тонкий entrypoint
│  └─ build_css.py            # сборка Tailwind standalone CLI
├─ assets/
│  ├─ icons.svg               # единый спрайт всех иконок танков
│  ├─ app.css                 # собранный Tailwind
│  ├─ input.css               # исходники CSS
│  ├─ app.js                  # вынесенный клиентский JS
│  └─ vendor/chart.umd.min.js
├─ tailwind.config.js
├─ tests/
│  └─ test_pipeline.py
├─ docs/ARCHITECTURE.md
├─ index.html
├─ requirements.txt
├─ README.md
└─ agents.md
```

## Контуры данных

### 1. Метаданные (`sync-vehicles.yml`)

Источник: Poliroid vehicles API. Официальный Lesta API остаётся резервным вариантом, пока не подключён.

Результат: `data/vehicles.json`. Обновляется редко, коммитится в репозиторий. Контур планок читает этот файл с диска и не зависит от доступности API метаданных.

Поля: `id`, `tag`, `nation`, `type`, `tier`, `name`, `short_name`, `is_premium`, `is_special`, `is_collector`, `role`.

### 2. Планки (`sync-marks.yml`)

Источник: Poliroid gunmarks API.

Результат: `data/latest.json` и `data/history/{tank_id}.json`.

Порядок:
1. Загрузить планки.
2. Смержить с `vehicles.json` по `id`.
3. Проверить Pydantic-схемой.
4. Проверить инварианты и аномалии.
5. Собрать `latest.json` в памяти.
6. Записать историю и `latest.json` через временный файл + `os.replace`.

## Контракты данных

### `latest.json`

```json
{
  "updated_at": "2026-11-22T02:25:56Z",
  "version": 8,
  "icons_url": "https://cdn.poliroid.me/icons/tanks_svg/ru",
  "vehicles": [
    {
      "id": 2049,
      "tag": "r12_a-20",
      "nation": "ussr",
      "type": "lightTank",
      "tier": 5,
      "name": "А-20",
      "short_name": "А-20",
      "is_premium": false,
      "is_special": false,
      "is_collector": false,
      "role": "",
      "marks": { "65": 484, "85": 812, "95": 1122, "100": 1422 }
    }
  ]
}
```

### `history/{tank_id}.json`

```json
[
  { "date": "2026-11-21", "65": 481, "85": 810, "95": 1124, "100": 1424 },
  { "date": "2026-11-22", "65": 484, "85": 812, "95": 1122, "100": 1422 }
]
```

Одна точка на календарный день UTC. Максимум 365 точек.

## Валидация

Pydantic проверяет типы и диапазоны. Отдельный слой проверяет логику:

1. `0 < 65 < 85 < 95 <= 100`.
2. Все четыре значения — целые, не больше разумного потолка (например, 50 000).
3. Нет дублей `id`, нет неизвестных `id`.
4. Пул не просел: не меньше 95% техники из `vehicles.json`.
5. Ни один уровень, класс и нация не потеряли больше 20% состава.
6. Дневной скачок: `abs(new - old) <= max(300, 15% old)`. Аномалия отбрасывается и логируется, а не молча принимается.
7. `100` не меньше `95`.

При провале валидации `latest.json` не трогается, workflow падает, ошибки уходят в stderr. Предупреждения (включая скачки) попадают в `data/meta.json`.

Запуск: `python scripts/update.py marks` (по умолчанию), `python scripts/update.py vehicles`, `python scripts/update.py icons`. Если `vehicles.json` отсутствует, контур марок создаёт его из API.

Иконки танков собраны в `assets/icons.svg`: один запрос вместо 787, внутренние `id` и CSS-классы изолированы префиксом символа. Пересборка — команда `icons`; при росте справочника её нужно добавить в `sync-vehicles.yml`.

## Атомарность

```python
tmp = path.with_name(path.name + ".tmp")
with open(tmp, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    handle.flush()
    os.fsync(handle.fileno())
os.replace(tmp, path)
```

История и `latest.json` пишутся только после успешной валидации всего снимка. `os.replace` атомарен в пределах одной файловой системы.

## Workflows

- `sync-marks.yml` — 2 раза в день, обновляет `latest.json`, `meta.json`, историю.
- `sync-vehicles.yml` — 1-е число месяца, обновляет `vehicles.json`.
- `deploy.yml` — по `workflow_run` успешных контуров, по push в `main` (пути `index.html`, `assets/**`, `data/**`) и вручную; собирает `_site`. `workflow_run` нужен, потому что push от `github-actions[bot]` не запускает другие workflow.
- `concurrency: group: data-sync, cancel-in-progress: false` — исключает параллельные коммиты обоих контуров.
- `permissions: contents: write` только у job обновления.
- Retry на сетевые ошибки: 3 попытки с экспоненциальной паузой.
- Перед обновлением данных в CI прогоняются `python -m unittest discover -s tests`.
- `pip install -r requirements.txt` вместо неиспользуемого `requests`.

## Фронтенд

- Все фильтры, поиск и сортировка — в браузере.
- `fetch` с `cache: 'no-cache'` вместо `?v=Date.now()`: GitHub Pages отдаёт ETag, лишние 200 КБ на каждый визит не нужны.
- Иконки берутся из `icons_url` в `latest.json`, а не из захардкоженного URL.
- Названия из внешнего API экранируются перед `innerHTML`.
- Tailwind собран в `assets/app.css`, Play CDN удалён. Пересборка: `python scripts/build_css.py` — standalone CLI без Node.js, бинарник кэшируется в `.cache/tailwind/`.
- Состояние фильтров дублируется в URL (`?tier=10,11&nation=ussr&sort=m95.desc`) и в `localStorage`. Дискретные изменения пишут `pushState`, поиск — `replaceState` с задержкой. Кнопка «Назад» восстанавливает фильтры. При загрузке URL имеет приоритет над `localStorage`.

## Текущие фильтры

- Уровни V–XI: мультиселект. Пустой набор = все. XI уровень подсвечен янтарным кантом.
- Класс: одиночный выбор.
- Тип получения: прокачиваемый / премиум и акционный.
- Нация: кастомный dropdown в палитре сайта, 12 наций, список строится по фактическим данным.
- Поиск: name, short_name, tag и точный id. Нормализация `ё/е`, пунктуации и пробелов; поиск по «сжатой» строке (`ИС-7` = `ис7`); транслитерация в обе стороны и конвертация раскладки QWERTY/ЙЦУКЕН; сленговые алиасы (несколько на танк, библиотека `SLANG_MAP` сгруппирована по нациям). Идентификатор сравнивается только целиком.

Боевая роль остаётся в данных и отображается в карточке танка, но фильтр по ней временно убран.
