"""Kiểm tra quy tắc hồi quy và ghi nhận đường rò ở văn bản tự do (chưa sửa khử danh)."""
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('wp6_grade', ROOT / 'eval' / 'wp6_grade.py')
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)
cases = json.loads((ROOT / 'eval' / 'wp6_cases.json').read_text(encoding='utf-8'))


class GradeTests(unittest.TestCase):
    def test_supported_and_abstention(self):
        self.assertEqual(grader.grade(cases[0], 'Chế phẩm giả định A: 12 mg [1].'), [])
        self.assertEqual(grader.grade(cases[1], 'Nguồn không đề cập.'), [])
        self.assertEqual(grader.grade(cases[2], 'Nguồn không đề cập.'), [])

    def test_invalid_citation_and_unsupported_dose(self):
        errors = grader.grade(cases[0], 'Liều 24 mg [3].')
        self.assertEqual(len(errors), 2)
        self.assertTrue(grader.grade(cases[1], 'Liều 10 mg [1].'))

    def test_patient_history_box_is_optional_and_wrapped(self):
        spec = importlib.util.spec_from_file_location('wp6_patient_context', ROOT / 'backend' / 'patient_context.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.build_prompt_block('   '), (None, ''))
        raw, block = mod.build_prompt_block('THA 10 năm, đang dùng amlodipin. Dị ứng penicillin.')
        self.assertIn('amlodipin', raw)
        self.assertTrue(block.startswith('<tien_su_benh_nhan>'))
        # Chỉ phần nói về dị ứng đi vào bộ đối chiếu dị ứng, không kèm thuốc đang dùng.
        self.assertEqual(mod.allergy_text('THA, đang dùng amlodipin; Dị ứng penicillin'), 'Dị ứng penicillin')
        self.assertIsNone(mod.allergy_text('THA, đang dùng amlodipin'))


if __name__ == '__main__':
    unittest.main()
