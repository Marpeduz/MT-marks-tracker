import json
import os

from .config import HISTORY_DAYS, HISTORY_DIR
from .models import Marks


def atomic_write_json(path, payload) -> None:
    """Пишет JSON через временный файл. Читатель видит либо старый, либо новый файл."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def history_path(tank_id: int):
    return HISTORY_DIR / f"{tank_id}.json"


def load_history(tank_id: int) -> list[dict]:
    path = history_path(tank_id)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def append_point(history: list[dict], date: str, marks: Marks) -> list[dict]:
    if history and history[-1].get("date") == date:
        return history

    result = list(history)
    result.append({"date": date, **marks.as_public()})
    return result[-HISTORY_DAYS:]


def write_history(updates: dict[int, Marks], date: str) -> int:
    written = 0
    for tank_id, marks in updates.items():
        history = load_history(tank_id)
        updated = append_point(history, date, marks)
        if updated == history:
            continue
        atomic_write_json(history_path(tank_id), updated)
        written += 1
    return written
