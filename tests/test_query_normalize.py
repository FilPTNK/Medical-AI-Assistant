"""Gỡ Telex và khôi phục dấu chỉ bằng từ vựng của kho."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import query_normalize as qn  # noqa: E402

CORPUS = [
    'Thuốc hạ huyết áp dùng cho trẻ em cần giảm liều.',
    'Đái tháo đường type 2: thuốc hạ glucose huyết.',
    'Không dùng aspirin cho trẻ em dưới 12 tuổi.',
    'Thuốc giảm đau, hạ sốt. Liều dùng cho trẻ em.',
    'Chiều dài, dài hơn, dài ngày.',
] * 8 + ['gif trer']  # rác OCR trông như Telex: hiếm hơn "trẻ" (24 lần) quá TELEX_MIN_RATIO


class NormalizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = qn.QueryLexicon.build(CORPUS)

    def norm(self, q):
        return self.lex.normalize(q).text

    def test_unaccented_query_is_restored(self):
        self.assertEqual(self.norm('thuoc ha huyet ap cho tre em'), 'thuốc hạ huyết áp cho trẻ em')

    def test_context_picks_the_medical_reading(self):
        # "dai" một mình hay gặp là "dài"; đứng trước "tháo đường" thì là "đái".
        self.assertEqual(self.norm('dai thao duong'), 'đái tháo đường')

    def test_accented_query_untouched(self):
        for q in ['Thuốc hạ sốt cho trẻ em', 'Liều dùng aspirin']:
            self.assertEqual(self.norm(q), q)

    def test_unknown_words_kept(self):
        self.assertEqual(self.norm('lieu dung cefixime'), 'liều dùng cefixime')

    def test_telex_fixed_only_when_corpus_confirms(self):
        self.assertEqual(self.norm('thuoocs giamr ddau'), 'thuốc giảm đau')
        self.assertEqual(self.norm('aspirin'), 'aspirin')

    def test_telex_beats_rare_ocr_junk(self):
        self.assertEqual(self.lex.fix_telex('trer'), 'trẻ')

    def test_segment_folded(self):
        df = {'dai_thao_duong': 3, 'tre_em': 5}
        self.assertEqual(qn.segment_folded(['dai', 'thao', 'duong', 'o', 'tre', 'em'], df),
                         ['dai_thao_duong', 'o', 'tre_em'])


if __name__ == '__main__':
    unittest.main()
