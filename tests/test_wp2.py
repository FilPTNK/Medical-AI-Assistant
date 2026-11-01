"""Kiểm tra thay đổi tất định; pytest thu thập được, unittest chạy được khi thiếu pytest."""
import sys
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))
import query_intent as qi
import eval_set_wp2


class QueryIntentTests(unittest.TestCase):
    def test_only_explicit_indication(self):
        self.assertEqual(qi.indication_subject("thuốc giảm đau bụng"), "đau bụng")
        self.assertIsNone(qi.indication_subject("Ibuprofen khi mang thai"))
        self.assertIsNone(qi.indication_subject("thuốc không giảm đau bụng"))

    def test_indications_boost_requires_literal_subject(self):
        base = 0.02
        meta = {"field_type": "INDICATIONS", "drug_class": "x"}
        self.assertGreater(qi.adjusted_score(base, meta, "Giảm đau bụng", "đau bụng"), base)
        self.assertEqual(qi.adjusted_score(base, meta, "Chỉ định khác", "đau bụng"), base)
        self.assertEqual(qi.adjusted_score(base, {"field_type": "DOSAGE"}, "đau bụng", "đau bụng"), base)

    def test_flag_and_unreviewed_terms(self):
        self.assertEqual(qi.expanded_terms("đau bụng"), ())
        with mock.patch.object(qi, "ENABLE_INDICATION_RANKING", False):
            self.assertEqual(qi.adjusted_score(0.02, {"field_type": "INDICATIONS"}, "đau bụng", "đau bụng"), 0.02)
        self.assertEqual(qi.APPROVED_CLASS_EXCLUSIONS, {})

    def test_evaluation_count_and_review(self):
        self.assertEqual(len(eval_set_wp2.QUERIES), 80)
        self.assertEqual({x[3] for x in eval_set_wp2.QUERIES},
                         {"hoạt chất", "tên biệt dược/thuốc", "triệu chứng/chỉ định", "thận trọng"})
        self.assertTrue(all(q[1] and q[2] and q[4] == eval_set_wp2.REVIEW
                            for q in eval_set_wp2.QUERIES))


if __name__ == "__main__":
    unittest.main()
