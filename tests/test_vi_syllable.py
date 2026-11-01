"""Bộ kiểm âm tiết tiếng Việt (vi_syllable.py)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import vi_syllable as v  # noqa: E402


class SyllableTests(unittest.TestCase):
    def test_valid_words(self):
        for w in ('thuốc liều dùng người lớn trẻ em suy thận chống chỉ định gì quả giữa '
                  'nghiêng khuỷu thuyền tuần quyết oách hoà hòa thủy thuỷ được Đường').split():
            self.assertTrue(v.is_valid(w), w)

    def test_stop_coda_needs_sac_or_nang(self):
        self.assertFalse(v.is_valid('thuôc'))   # OCR mất dấu sắc
        self.assertFalse(v.is_valid('mạch'.replace('ạ', 'à')))
        self.assertTrue(v.is_valid('mạch'))

    def test_tone_on_wrong_vowel_or_twice(self):
        self.assertFalse(v.is_valid('nhỉêm'))
        self.assertFalse(v.is_valid('ngươì'))
        self.assertFalse(v.is_valid('liềú'))

    def test_foreign_words_not_counted(self):
        s = v.page_score('Augmentin 500 mg amoxicillin')
        self.assertEqual(s['invalid'], 0)

    def test_page_score(self):
        s = v.page_score('Liều dùng cho trẻ thuôc nhỉêm')
        self.assertEqual((s['judged'], s['invalid']), (6, 2))


if __name__ == '__main__':
    unittest.main()
