import json
import time
import urllib.request

from .config import (
    MARKS_URL,
    REQUEST_RETRIES,
    REQUEST_TIMEOUT,
    USER_AGENT,
    VEHICLES_URL,
)


class SourceError(RuntimeError):
    """Источник недоступен или вернул неожиданный ответ."""


def fetch_json(url: str) -> dict:
    last_error = None

    for attempt in range(1, REQUEST_RETRIES + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise SourceError(f"ожидался JSON-объект, получен {type(payload).__name__}")
            return payload
        except Exception as exc:  # сеть, таймаут, битый JSON
            last_error = exc
            if attempt < REQUEST_RETRIES:
                time.sleep(2 ** (attempt - 1))

    raise SourceError(f"не удалось загрузить {url} за {REQUEST_RETRIES} попыток: {last_error}")


def _require_ok(payload: dict, source: str) -> dict:
    if payload.get("status") != "ok":
        raise SourceError(f"{source}: status != ok")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SourceError(f"{source}: отсутствует секция data")
    return data


def fetch_vehicles() -> tuple[dict, list]:
    """Возвращает (meta, список строк техники) из справочника."""
    data = _require_ok(fetch_json(VEHICLES_URL), "vehicles")
    inner = data.get("data") or {}
    rows = inner.get("vehicles") or []
    if not isinstance(rows, list):
        raise SourceError("vehicles: vehicles не список")
    return (data.get("meta") or {}, rows)


def fetch_marks() -> list:
    """Возвращает список записей с планиками марок."""
    data = _require_ok(fetch_json(MARKS_URL), "marks")
    items = data.get("data")
    if not isinstance(items, list):
        raise SourceError("marks: data не список")
    return items
