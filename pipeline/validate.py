from dataclasses import dataclass, field

from pydantic import ValidationError

from .config import (
    MARK_KEYS,
    MAX_SECTION_DROP,
    MIN_POOL_RATIO,
    MIN_SECTION_SIZE_FOR_CHECK,
    MIN_TIER,
    MIN_VEHICLES,
    SPIKE_ABS,
    SPIKE_REL,
)
from .models import LatestSnapshot, Marks, VehicleMeta, VehicleSnapshot, VehiclesCatalog


class ValidationFailure(RuntimeError):
    """Снимок не прошёл проверку и не должен публиковаться."""


@dataclass
class ValidationResult:
    accepted: list[VehicleSnapshot] = field(default_factory=list)
    history_updates: dict[int, Marks] = field(default_factory=dict)
    skipped_history: set[int] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_catalog(meta: dict, rows: list, updated_at: str) -> tuple[VehiclesCatalog, list[str]]:
    """Собирает статический справочник из ответа API."""
    vehicles: list[VehicleMeta] = []
    warnings: list[str] = []
    seen: set[int] = set()

    for row in rows:
        if not isinstance(row, list) or len(row) < 12:
            warnings.append("пропущена строка справочника: неверная структура")
            continue

        tier, tankopedia = row[4], row[11]
        if not isinstance(tier, int) or not (MIN_TIER <= tier <= 11) or tankopedia != 1:
            continue

        try:
            vehicle = VehicleMeta(
                id=row[0],
                tag=row[1] or "",
                nation=row[2],
                type=row[3],
                tier=tier,
                name=row[5],
                short_name=row[6] or "",
                is_premium=bool(row[8]),
                is_special=bool(row[9]),
                is_collector=bool(row[10]),
                role=row[12] if len(row) > 12 else "",
            )
        except ValidationError as exc:
            warnings.append(f"пропущен tank_id={row[0]}: {exc.errors()[0]['msg']}")
            continue

        if vehicle.id in seen:
            warnings.append(f"пропущен дубль tank_id={vehicle.id}")
            continue
        seen.add(vehicle.id)
        vehicles.append(vehicle)

    if len(vehicles) < MIN_VEHICLES:
        raise ValidationFailure(
            f"справочник слишком мал: {len(vehicles)} танков, минимум {MIN_VEHICLES}"
        )

    catalog = VehiclesCatalog(
        updated_at=updated_at,
        version=int(meta.get("version") or 1),
        icons_url=meta.get("icons_url") or "",
        vehicles=vehicles,
    )
    return catalog, warnings


def load_baseline(raw: dict | None) -> LatestSnapshot | None:
    if not raw:
        return None
    try:
        return LatestSnapshot.model_validate(raw)
    except ValidationError:
        return None


def is_spike(new: Marks, previous: dict) -> bool:
    for key in MARK_KEYS:
        value = getattr(new, f"m{key}")
        old = previous.get(key)
        if not isinstance(old, (int, float)):
            continue
        limit = max(SPIKE_ABS, abs(old) * SPIKE_REL)
        if abs(value - old) > limit:
            return True
    return False


def _value(item, key: str):
    if hasattr(item, key):
        return getattr(item, key)
    if isinstance(item, dict):
        return item.get(key)
    return None


def section_counts(vehicles) -> dict[tuple[str, object], int]:
    counts: dict[tuple[str, object], int] = {}
    for vehicle in vehicles:
        for key in ("tier", "type", "nation"):
            section = (key, _value(vehicle, key))
            counts[section] = counts.get(section, 0) + 1
    return counts


def check_pool(accepted: list[VehicleSnapshot], catalog: VehiclesCatalog, baseline, errors: list[str]) -> None:
    expected_ids = {v.id for v in catalog.vehicles}
    actual_ids = {v.id for v in accepted}

    if len(actual_ids) < MIN_VEHICLES:
        errors.append(f"получено слишком мало танков: {len(actual_ids)}, минимум {MIN_VEHICLES}")

    if expected_ids and len(actual_ids) / len(expected_ids) < MIN_POOL_RATIO:
        errors.append(
            f"пул техники просел: {len(actual_ids)} из {len(expected_ids)} "
            f"({len(actual_ids) / len(expected_ids):.1%}, минимум {MIN_POOL_RATIO:.0%})"
        )

    if baseline is None:
        return

    old_counts = section_counts(baseline.vehicles)
    new_counts = section_counts(accepted)
    for section, old_count in old_counts.items():
        if old_count < MIN_SECTION_SIZE_FOR_CHECK:
            continue
        new_count = new_counts.get(section, 0)
        if new_count < old_count * (1 - MAX_SECTION_DROP):
            errors.append(
                f"секция {section[0]}={section[1]} просела: {old_count} -> {new_count}"
            )


def validate_marks(items: list, catalog: VehiclesCatalog, history_loader, baseline) -> ValidationResult:
    result = ValidationResult()
    meta_by_id = {v.id: v for v in catalog.vehicles}
    seen: set[int] = set()

    for item in items:
        if not isinstance(item, dict):
            result.warnings.append("пропущена запись marks: неверная структура")
            continue

        tank_id = item.get("id")
        if tank_id in seen:
            result.warnings.append(f"пропущен дубль tank_id={tank_id}")
            continue
        seen.add(tank_id)

        if tank_id not in meta_by_id:
            result.warnings.append(f"пропущен неизвестный tank_id={tank_id}")
            continue

        try:
            marks = Marks.model_validate(item.get("marks") or {})
        except ValidationError as exc:
            result.warnings.append(f"пропущены marks tank_id={tank_id}: {exc.errors()[0]['msg']}")
            continue

        history = history_loader(tank_id) or []
        previous = history[-1] if history else None
        snapshot = VehicleSnapshot(**meta_by_id[tank_id].model_dump(), marks=marks)

        if previous and is_spike(marks, previous):
            try:
                restored = Marks.model_validate(previous)
            except ValidationError:
                result.warnings.append(
                    f"tank_id={tank_id}: аномальный скачок, но предыдущая запись битая — пропущен"
                )
                continue
            result.warnings.append(
                f"tank_id={tank_id}: аномальный скачок {marks.as_public()} -> {restored.as_public()}, "
                "взято предыдущее значение"
            )
            snapshot = VehicleSnapshot(**meta_by_id[tank_id].model_dump(), marks=restored)
            result.skipped_history.add(tank_id)

        result.accepted.append(snapshot)
        if tank_id not in result.skipped_history:
            result.history_updates[tank_id] = marks

    check_pool(result.accepted, catalog, baseline, result.errors)
    return result
