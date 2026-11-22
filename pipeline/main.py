import argparse
import sys
from datetime import datetime, timezone

from .build import build_latest, build_meta, load_json
from .config import (
    DEFAULT_ICONS_URL,
    ICONS_SPRITE_PATH,
    LATEST_PATH,
    META_PATH,
    VEHICLES_PATH,
)
from .history import atomic_write_json, load_history, write_history
from .icons import build_sprite
from .models import VehiclesCatalog
from .sources import SourceError, fetch_marks, fetch_vehicles
from .validate import ValidationFailure, load_baseline, parse_catalog, validate_marks


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def refresh_vehicles() -> None:
    """Редкий контур: обновляет статический справочник техники."""
    meta, rows = fetch_vehicles()
    catalog, warnings = parse_catalog(meta, rows, utc_now())

    atomic_write_json(VEHICLES_PATH, catalog.model_dump(mode="json"))

    print(f"Справочник обновлён: {len(catalog.vehicles)} танков V-XI уровней.")
    for warning in warnings[:10]:
        print(f"  ! {warning}")
    if len(warnings) > 10:
        print(f"  ... и ещё {len(warnings) - 10}")


def update_marks() -> None:
    """Частый контур: обновляет планки и историю по локальному справочнику."""
    raw_catalog = load_json(VEHICLES_PATH)
    if not raw_catalog:
        print("vehicles.json не найден, восстанавливаю справочник из API.")
        refresh_vehicles()
        raw_catalog = load_json(VEHICLES_PATH)

    catalog = VehiclesCatalog.model_validate(raw_catalog)
    items = fetch_marks()

    baseline = load_baseline(load_json(LATEST_PATH))
    result = validate_marks(items, catalog, load_history, baseline)

    if result.errors:
        raise ValidationFailure("\n".join(result.errors))

    now = utc_now()
    latest = build_latest(result.accepted, catalog, now)
    history_written = write_history(result.history_updates, now[:10])

    # Публикуем снимок только после успешной записи истории
    atomic_write_json(LATEST_PATH, latest)
    atomic_write_json(META_PATH, build_meta(now, catalog, result, history_written))

    print(
        f"latest.json обновлён: {len(result.accepted)} танков, "
        f"история: +{history_written} точек, предупреждений: {len(result.warnings)}."
    )
    for warning in result.warnings[:10]:
        print(f"  ! {warning}")
    if len(result.warnings) > 10:
        print(f"  ... и ещё {len(result.warnings) - 10}")


def refresh_icons() -> None:
    """Собирает все иконки в один локальный SVG-спрайт."""
    catalog = VehiclesCatalog.model_validate(load_json(VEHICLES_PATH))
    summary = build_sprite(
        [vehicle.tag for vehicle in catalog.vehicles],
        ICONS_SPRITE_PATH,
        catalog.icons_url or DEFAULT_ICONS_URL,
    )
    print(
        f"Спрайт иконок собран: {summary['built']}/{summary['total']} иконок, "
        f"файл {ICONS_SPRITE_PATH}."
    )
    if summary["failed"]:
        print(f"Не загружены теги: {', '.join(summary['failed'][:20])}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Обновление данных отметок Мир Танков")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("marks", "vehicles", "icons"),
        default="marks",
        help="marks — планки (по умолчанию), vehicles — справочник, icons — спрайт иконок",
    )
    args = parser.parse_args(argv)

    try:
        if args.command == "vehicles":
            refresh_vehicles()
        elif args.command == "icons":
            refresh_icons()
        else:
            update_marks()
    except (SourceError, ValidationFailure) as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
