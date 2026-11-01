"""Giai đoạn 3: tách câu hỏi nhiều điều kiện, trích nguyên văn, tô theo con số, bảng kiểm."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import page_locate  # noqa: E402
import query_plan as qp  # noqa: E402

AMOX = ([('amoxicilin',)], 'Amoxicilin', ['amoxicilin'])
WARF = ([('warfarin',)], 'Warfarin', ['warfarin'])


class PlanTests(unittest.TestCase):
    def test_two_slots_two_conditions(self):
        conds = qp.plan(['dosage'], ['child', 'renal'], [AMOX])
        self.assertEqual([c.cid for c in conds], ['child', 'renal'])
        # "Liều …": tìm ở mục Liều trước.
        self.assertTrue(all(c.sections[0] == 'DOSAGE' for c in conds))
        self.assertTrue(all(c.need_number and c.verbatim for c in conds))

    def test_contraindication_intent_reorders_sections(self):
        (c,) = qp.plan(['contraindication'], ['hepatic'], [AMOX])
        self.assertEqual(c.sections[0], 'CONTRAINDICATION')
        self.assertFalse(c.need_number)

    def test_no_drug_no_plan(self):
        self.assertEqual(qp.plan(['dosage'], ['renal'], []), [])

    def test_intent_without_slot(self):
        (c,) = qp.plan(['adr'], [], [AMOX])
        self.assertEqual((c.cid, c.sections), ('adr', ('ADR', 'ADR_MANAGEMENT')))

    def test_pregnancy_not_duplicated(self):
        conds = qp.plan(['pregnancy'], ['pregnancy'], [AMOX])
        self.assertEqual([c.cid for c in conds], ['pregnancy'])

    def test_interaction_pair(self):
        (c,) = qp.plan(['interaction'], [], [AMOX, WARF])
        self.assertEqual(c.cid, 'interaction_pair')
        self.assertIsNotNone(c.pair)


class MentionTests(unittest.TestCase):
    def test_folded_and_word_boundary(self):
        renal = qp.CONDITIONS['renal'][2]
        self.assertEqual(qp.mentions_any('Bệnh nhân suy than nặng', renal), 1)  # OCR rụng dấu
        self.assertEqual(qp.mentions_any('Thận trọng khi dùng', renal), 0)
        self.assertEqual(qp.mentions_any('Thải trừ qua thận', qp.CONDITIONS['pregnancy'][2]), 0)

    def test_age_needs_a_number(self):
        # "tươi" và "tuổi" cùng gấp ra "tuoi": "sữa tươi" không phải điều kiện trẻ em.
        child = qp.CONDITIONS['child'][2]
        self.assertEqual(qp.mentions_any('trộn với sữa bột, sữa tươi', child), 0)
        self.assertEqual(qp.mentions_any('Từ 3 tháng đến 12 tuổi: 25 mg/kg', child), 1)
        self.assertEqual(qp.mentions_any('Dưới 6 thang tuoi không dùng', child), 1)

    def test_body_of_strips_parser_header(self):
        text = '【THUỐC: AMOXICILIN】 (Dược thư) [Liều lượng và cách dùng] Người lớn: 500 mg.'
        self.assertEqual(qp.body_of(text), 'Người lớn: 500 mg.')
        self.assertEqual(qp.body_of('LD: Uống 1 viên mỗi ngày.'), 'Uống 1 viên mỗi ngày.')


class QuoteTests(unittest.TestCase):
    CHUNK = ('[Liều lượng và cách dùng] Người lớn uống 500 mg mỗi 8 giờ. '
             'Suy thận: thận trọng khi dùng kéo dài. '
             'Suy thận với ClCr 10-30 ml/phút: 250-500 mg mỗi 12 giờ. '
             'Trẻ em dùng theo cân nặng.')

    def test_only_sentences_mentioning_condition(self):
        renal = qp.plan(['dosage'], ['renal'], [AMOX])[0]
        quotes = qp.pick_quotes(self.CHUNK, renal)
        self.assertTrue(quotes)
        self.assertTrue(all('thận' in q.lower() for q in quotes))

    def test_number_preferred_and_verbatim(self):
        renal = qp.plan(['dosage'], ['renal'], [AMOX])[0]
        quotes = qp.pick_quotes(self.CHUNK, renal)
        self.assertIn('Suy thận với ClCr 10-30 ml/phút: 250-500 mg mỗi 12 giờ.', quotes)

    def test_condition_absent_no_quote(self):
        hep = qp.plan(['dosage'], ['hepatic'], [AMOX])[0]
        self.assertEqual(qp.pick_quotes(self.CHUNK, hep), [])


def _words(text):
    return [{'t': t, 'line': '0', 'x0': i, 'y0': 0, 'x1': i + 1, 'y1': 1}
            for i, t in enumerate(text.split())]


class LocateTests(unittest.TestCase):
    def test_numbers_split_from_units(self):
        self.assertEqual(page_locate._fine('500mg'), ['500', 'mg'])
        self.assertEqual(page_locate._fine('10-15 mg/kg'), ['10', '15', 'mg', 'kg'])

    def test_anchor_picks_sentence_with_same_numbers(self):
        # Hai câu gần giống nhau chỉ khác số: phải tô câu có đúng số.
        page = ('Trẻ em uống 10 mg/kg mỗi 6 giờ khi sốt cao. '
                'Một đoạn chèn giữa để tách hai câu ra xa nhau đủ dài cho phép dóng. '
                'Trẻ em uống 15 mg/kg mỗi 8 giờ khi sốt cao.')
        words = _words(page)
        old = page_locate.ANCHOR_NUMBERS
        try:
            page_locate.ANCHOR_NUMBERS = True
            r = page_locate.locate(words, 'Trẻ em uống 15 mg/kg mỗi 8 giờ khi sốt cao.')
        finally:
            page_locate.ANCHOR_NUMBERS = old
        a, b = r['span']
        span_text = ' '.join(w['t'] for w in words[a:b + 1])
        self.assertIn('15', span_text)
        self.assertNotIn('10', span_text)

    def test_no_highlight_when_numbers_missing(self):
        # Trang chỉ có câu chữ giống nhưng gần như không có số của câu trích: không tô.
        words = _words('Hiệu chỉnh liều thích hợp khi suy thận nặng (mức lọc dưới 30 ml/phút) hoặc thẩm tách.')
        r = page_locate.locate(words, 'Hiệu chỉnh liều khi suy thận: 10 - 30 ml/phút, sau đó 500 - 1000 mg mỗi 12 giờ.')
        self.assertEqual(r['rects'], [])


class CoverageNotesTests(unittest.TestCase):
    def setUp(self):
        try:
            import llm_client
        except Exception as e:  # thiếu thư viện gọi mô hình trong môi trường thử
            self.skipTest(f'llm_client: {e}')
        self.notes = llm_client.coverage_notes

    def test_empty(self):
        self.assertEqual(self.notes(None), '')
        self.assertEqual(self.notes([]), '')

    def test_found_partial_missing(self):
        text = self.notes([
            {'label': 'Trẻ em', 'drug': 'Amoxicilin', 'found': True, 'source_index': 0,
             'in_preferred_section': True},
            {'label': 'Suy gan', 'drug': 'Amoxicilin', 'found': True, 'source_index': 2,
             'in_preferred_section': False, 'section': 'Thận trọng'},
            {'label': 'Suy thận', 'drug': 'Amoxicilin', 'found': False},
        ])
        self.assertIn('Trẻ em (Amoxicilin): có ở nguồn [1]', text)
        self.assertIn("mục 'Thận trọng' (nguồn [3])", text)
        self.assertIn('Thư viện không có thông tin về suy thận cho Amoxicilin', text)


if __name__ == '__main__':
    unittest.main()
