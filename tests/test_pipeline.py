import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from pipeline.build import build_latest
from pipeline.history import atomic_write_json
from pipeline.models import Marks, VehicleMeta, VehicleSnapshot, VehiclesCatalog
from pipeline.validate import (
    ValidationFailure,
    is_spike,
    parse_catalog,
    validate_marks,
)


def make_row(tank_id=1, tier=8, tankopedia=1, name="Test", role="role_MT_universal"):
    return [
        tank_id, f"tag_{tank_id}", "ussr", "mediumTank", tier, name, name,
        0, 0, 0, 1, tankopedia, role,
    ]


def make_vehicle(tank_id=1):
    return VehicleMeta(
        id=tank_id,
        tag=f"tag_{tank_id}",
        nation="ussr",
        type="mediumTank",
        tier=8,
        name="Test",
        role="role_MT_universal",
    )


class MarksTests(unittest.TestCase):
    def test_thresholds_must_increase(self):
        with self.assertRaises(ValidationError):
            Marks(**{"65": 100, "85": 100, "95": 100, "100": 100})

    def test_valid_marks_and_public_view(self):
        marks = Marks(**{"65": 100, "85": 200, "95": 300, "100": 400})
        self.assertEqual(marks.as_public(), {"65": 100, "85": 200, "95": 300, "100": 400})


class SpikeTests(unittest.TestCase):
    def test_small_change_is_not_spike(self):
        marks = Marks(**{"65": 100, "85": 200, "95": 300, "100": 400})
        self.assertFalse(is_spike(marks, {"65": 100, "85": 200, "95": 300, "100": 400}))

    def test_big_change_is_spike(self):
        marks = Marks(**{"65": 100, "85": 200, "95": 900, "100": 1000})
        self.assertTrue(is_spike(marks, {"65": 100, "85": 200, "95": 300, "100": 400}))


class CatalogTests(unittest.TestCase):
    def test_filters_by_tier_and_tankopedia(self):
        rows = [
            make_row(1, tier=8, tankopedia=1),
            make_row(2, tier=4, tankopedia=1),
            make_row(3, tier=11, tankopedia=1),
            make_row(4, tier=8, tankopedia=0),
            make_row(1, tier=8, tankopedia=1),
        ]
        with patch("pipeline.validate.MIN_VEHICLES", 1):
            catalog, warnings = parse_catalog({"version": 8, "icons_url": "u"}, rows, "now")

        self.assertEqual([v.id for v in catalog.vehicles], [1, 3])
        self.assertTrue(any("дубль" in w for w in warnings))

    def test_too_small_catalog_is_rejected(self):
        with self.assertRaises(ValidationFailure):
            parse_catalog({}, [make_row(1)], "now")


class MarksValidationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = VehiclesCatalog(
            updated_at="now", version=8, icons_url="u", vehicles=[make_vehicle(1)]
        )

    def test_spike_falls_back_to_previous_value(self):
        items = [{"id": 1, "marks": {"65": 100, "85": 200, "95": 900, "100": 1000}}]
        history = {
            1: [{"date": "2026-11-21", "65": 100, "85": 200, "95": 300, "100": 400}]
        }
        result = validate_marks(items, self.catalog, lambda tid: history.get(tid, []), None)

        self.assertEqual(result.accepted[0].marks.as_public()["95"], 300)
        self.assertIn(1, result.skipped_history)
        self.assertEqual(result.history_updates, {})
        self.assertTrue(any("аномальный скачок" in w for w in result.warnings))

    def test_normal_value_writes_history(self):
        items = [{"id": 1, "marks": {"65": 100, "85": 200, "95": 300, "100": 400}}]
        with patch("pipeline.validate.MIN_VEHICLES", 1):
            result = validate_marks(items, self.catalog, lambda tid: [], None)

        self.assertEqual(len(result.accepted), 1)
        self.assertIn(1, result.history_updates)
        self.assertEqual(result.errors, [])

    def test_pool_shortage_is_an_error(self):
        catalog = VehiclesCatalog(
            updated_at="now",
            version=8,
            icons_url="u",
            vehicles=[make_vehicle(i) for i in range(1, 21)],
        )
        items = [{"id": i, "marks": {"65": 1, "85": 2, "95": 3, "100": 4}} for i in range(1, 3)]
        with patch("pipeline.validate.MIN_VEHICLES", 1), patch(
            "pipeline.validate.MIN_POOL_RATIO", 0.95
        ):
            result = validate_marks(items, catalog, lambda tid: [], None)

        self.assertTrue(any("пул техники просел" in e for e in result.errors))

    def test_unknown_and_duplicate_ids_are_skipped(self):
        items = [
            {"id": 1, "marks": {"65": 1, "85": 2, "95": 3, "100": 4}},
            {"id": 1, "marks": {"65": 1, "85": 2, "95": 3, "100": 4}},
            {"id": 999, "marks": {"65": 1, "85": 2, "95": 3, "100": 4}},
        ]
        result = validate_marks(items, self.catalog, lambda tid: [], None)
        self.assertEqual(len(result.accepted), 1)
        self.assertTrue(any("дубль" in w for w in result.warnings))
        self.assertTrue(any("неизвестный" in w for w in result.warnings))


class BuildTests(unittest.TestCase):
    def test_latest_shape(self):
        vehicle = VehicleSnapshot(**make_vehicle(1).model_dump(), marks=Marks(**{
            "65": 1, "85": 2, "95": 3, "100": 4,
        }))
        catalog = VehiclesCatalog(
            updated_at="now", version=8, icons_url="u", vehicles=[make_vehicle(1)]
        )
        latest = build_latest([vehicle], catalog, "2026-11-22T00:00:00Z")

        self.assertEqual(set(latest), {"updated_at", "version", "icons_url", "vehicles"})
        self.assertEqual(latest["vehicles"][0]["marks"], {"65": 1, "85": 2, "95": 3, "100": 4})
        self.assertEqual(
            set(latest["vehicles"][0]),
            {
                "id", "tag", "nation", "type", "tier", "name", "short_name",
                "is_premium", "is_special", "is_collector", "role", "marks",
            },
        )

    def test_atomic_write_leaves_no_tmp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "data.json"
            atomic_write_json(path, {"a": 1})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 1})
            self.assertFalse(Path(str(path) + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
