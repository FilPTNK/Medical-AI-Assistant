"""Cổng số liệu: con số liều trong câu trả lời phải có trong đúng trang được trích."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import answer_verify as av  # noqa: E402

PARA = {'text': 'Paracetamol. Người lớn: uống 500 mg - 1 g mỗi 4 - 6 giờ, tối đa 4 g/ngày. '
                'Trẻ em: 10 - 15 mg/kg mỗi 6 giờ.'}
AMOX = {'text': 'Amoxicilin: trẻ em dưới 40 kg uống 25 mg/kg/ngày chia 2 lần.'}


def statuses(answer, sources=(PARA, AMOX), **kw):
    return [(f['text'], f['status']) for f in av.verify_answer(answer, list(sources), **kw)['flags']]


class ExtractTests(unittest.TestCase):
    def test_ranges_units_and_per_kg(self):
        ds = av.extract_doses('10–15 mg/kg/ngày, 0,5 g, mỗi 8 giờ, 2 lần/ngày, 1.000 mg')
        self.assertEqual([d.keys() for d in ds], [
            [('mass', 10.0, '/kg'), ('mass', 15.0, '/kg')],
            [('mass', 500.0, '')],
            [('giờ', 8.0, '')],
            [('lần', 2.0, '')],
            [('mass', 1000.0, '')],
        ])

    def test_citation_numbers_are_not_doses(self):
        self.assertEqual(av.extract_doses('Liều dùng [1] theo trang 12 [2].'), [])


class VerifyTests(unittest.TestCase):
    def test_grounded_numbers_pass(self):
        self.assertEqual(statuses('Người lớn uống 500 mg đến 1 g mỗi 4–6 giờ, tối đa 4 g/ngày [1].'), [])

    def test_value_equivalence_across_units(self):
        # "1000 mg" là đúng "1 g" của sách — viết khác, cùng giá trị.
        self.assertEqual(statuses('Liều đơn tối đa 1000 mg [1].'), [])

    def test_changed_number_is_flagged(self):
        self.assertEqual(statuses('Tối đa 6 g/ngày [1].'), [('6 g/ngày', 'ungrounded')])

    def test_mg_mcg_swap_is_hard_error(self):
        self.assertEqual(statuses('Người lớn uống 500 mcg [1].'), [('500 mcg', 'unit_mismatch')])

    def test_per_kg_must_match(self):
        # Bỏ mất "/kg" là đổi liều theo cân nặng thành liều cố định.
        self.assertEqual(statuses('Trẻ em: 15 mg mỗi 6 giờ [1].'), [('15 mg', 'ungrounded')])

    def test_number_from_another_source(self):
        self.assertEqual(statuses('Trẻ dưới 40 kg dùng 25 mg/kg/ngày [1].'),
                         [('40 kg', 'other_source'), ('25 mg/kg/ngày', 'other_source')])

    def test_uncited_sentence_checks_all_sources(self):
        self.assertEqual(statuses('Trẻ dưới 40 kg dùng 25 mg/kg/ngày.'), [])

    def test_page_text_fallback(self):
        src = [{'text': 'Paracetamol (đoạn cắt ngắn).', 'doc_name': 'x', 'page_num': 3}]
        self.assertEqual(statuses('Tối đa 4 g/ngày [1].', src), [('4 g/ngày', 'ungrounded')])
        self.assertEqual(statuses('Tối đa 4 g/ngày [1].', src, page_text=lambda s: PARA['text']), [])

    def test_counts_checked(self):
        r = av.verify_answer('Uống 500 mg [1]. Không có số ở đây.', [PARA])
        self.assertEqual(r['checked'], 1)


if __name__ == '__main__':
    unittest.main()
