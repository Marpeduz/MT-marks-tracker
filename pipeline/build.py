import json

from .config import DEFAULT_ICONS_URL
from .models import VehiclesCatalog, VehicleSnapshot
from .validate import ValidationResult


def load_json(path):
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def build_latest(accepted: list[VehicleSnapshot], catalog: VehiclesCatalog, updated_at: str) -> dict:
    return {
        "updated_at": updated_at,
        "version": catalog.version,
        "icons_url": catalog.icons_url or DEFAULT_ICONS_URL,
        "vehicles": [vehicle.as_public() for vehicle in accepted],
    }


def build_meta(
    updated_at: str,
    catalog: VehiclesCatalog,
    result: ValidationResult,
    history_written: int,
) -> dict:
    return {
        "updated_at": updated_at,
        "catalog_count": len(catalog.vehicles),
        "vehicles_count": len(result.accepted),
        "history_points_written": history_written,
        "warnings": result.warnings[:50],
        "warning_count": len(result.warnings),
    }
