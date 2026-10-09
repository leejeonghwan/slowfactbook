import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from source_inventory import build, time_axis


class SourceInventoryTests(unittest.TestCase):
    def test_repeated_year_does_not_invent_months(self):
        frequency, quality, _ = time_axis(["2026"] * 12, None)
        self.assertEqual(frequency, "미확인")
        self.assertIn("원시점", quality)

    def test_registered_frequency_kept_separate_from_label_quality(self):
        frequency, quality, evidence = time_axis(["2026"] * 4, "M")
        self.assertEqual(frequency, "월")
        self.assertIn("원시점", quality)
        self.assertEqual(evidence, "연결 설정")

    def test_dates_do_not_prove_daily_release(self):
        self.assertEqual(time_axis(["2026-01-05", "2026-01-12"], None)[0], "일·주")

    def make_data(self, root):
        for name in ("ids", "overrides", "api_map", "api_map_auto", "api_charts", "kb_charts"):
            (root / (name + ".json")).write_text("{}")
        chart = {"id": "c1", "slide": "slide-1", "title": "편집자가 지은 제목", "vizType": "line", "labels": ["2025", "2026"], "seriesNames": ["계열 1"], "series": [[1, 2]]}
        (root / "full.json").write_text(json.dumps({"items": [chart]}))
        return chart

    def test_source_name_is_not_verified_or_automated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chart = self.make_data(root)
            chart["source"] = "통계청"
            (root / "full.json").write_text(json.dumps({"items": [chart]}))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            result = build(root, {})
            row = result["charts"][0]
            self.assertEqual(row["source_status"], "출처명만 있음")
            self.assertEqual(row["release_frequency"], "미확인")
            self.assertEqual(row["confirmed_check_frequency"], "미확정")
            self.assertFalse(row["match_verified"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_corrupt_input_reported_and_valid_items_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_data(root)
            (root / "api.json").write_text('{\n<<<<<<< HEAD')
            report = build(root, {})
            self.assertFalse(report["complete_input"])
            self.assertEqual(len(report["charts"]), 1)
            self.assertEqual(report["input_errors"][0]["file"], "api.json")

    def test_review_decision_invalidated_when_values_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chart = self.make_data(root)
            row = build(root, {})["charts"][0]
            reviews = {row["audit_key"]: {"fingerprint": row["fingerprint"], "confirmed_check_frequency": "연 1회"}}
            self.assertEqual(build(root, reviews)["charts"][0]["confirmed_check_frequency"], "연 1회")
            chart["series"] = [[1, 3]]
            (root / "full.json").write_text(json.dumps({"items": [chart]}))
            changed = build(root, reviews)["charts"][0]
            self.assertEqual(changed["confirmed_check_frequency"], "미확정")
            self.assertIn("재확인", changed["notes"])


if __name__ == "__main__":
    unittest.main()
