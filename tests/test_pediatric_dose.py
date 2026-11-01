"""Đọc liều mg/kg từ câu Dược thư — mỗi mệnh đề giữ tần suất và trần của chính nó."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import documents  # noqa: E402
import pediatric_dose as p  # noqa: E402


def lieu(text):
    return [(x['mg_kg_min'], x['mg_kg_max'], x['theo']) for x in p.doc_cau(text)]


class DocCauTests(unittest.TestCase):
    def test_each_clause_keeps_its_own_frequency(self):
        # Trước khi tách mệnh đề: 20 mg/kg nhận nhầm "cách 8 - 12 giờ" của liều sau.
        ds = p.doc_cau('Sơ sinh: 20 mg/kg một liều duy nhất; sau đó 10 - 15 mg/kg cách 8 - 12 giờ; '
                       'tối đa 60 mg/kg/ngày.')
        self.assertEqual([(x['mg_kg_min'], x['mg_kg_max']) for x in ds], [(20, 20), (10, 15)])
        self.assertTrue(ds[0]['mot_lieu'])
        self.assertIsNone(ds[0]['so_lan_ngay'])
        self.assertEqual(ds[1]['so_lan_ngay'], [2, 3])
        # Mệnh đề chỉ có trần áp cho các liều đứng trước nó.
        self.assertEqual([x['toi_da_mg_kg_ngay'] for x in ds], [60, 60])

    def test_per_day_dose_and_division(self):
        ds = p.doc_cau('Trẻ từ 1 tháng tuổi: 75 - 100 mg/kg/ngày chia làm 3 lần (tối đa 2,25 - 4,5 g/ngày)')
        self.assertEqual(lieu('Trẻ từ 1 tháng tuổi: 75 - 100 mg/kg/ngày chia làm 3 lần'), [(75, 100, 'ngay')])
        self.assertEqual(ds[0]['so_lan_ngay'], [3, 3])

    def test_max_per_dose_in_grams(self):
        ds = p.doc_cau('Trẻ > 6 tháng dùng liều duy nhất 30 mg/kg (tối đa 1,5 g).')
        self.assertEqual(ds[0]['toi_da_mg_lieu'], 1500)

    def test_ceiling_is_not_read_as_dose(self):
        self.assertEqual(lieu('Liều tiêm bắp một lần không được vượt quá 1 g ở người lớn hoặc 60 mg/kg ở trẻ em.'), [])
        self.assertEqual(lieu('Tối đa 30 mg/kg/ngày, chia 3 - 4 lần/ngày.'), [])

    def test_ocr_unit_variants(self):
        self.assertEqual(lieu('Liều một lần là 20 me/kg sau đó'), [(20, 20, 'lieu')])
        self.assertEqual(lieu('dùng liều 10 - 12 mg kg x 1 lần ngày'), [(10, 12, 'lieu')])
        self.assertEqual(lieu('tối đa 60 mg/ kg/24 giờ; 15 mg/kg/24 giờ'), [(15, 15, 'ngay')])
        ds = p.doc_cau('15 - 20 mg/kg cách nhau 4 - 6 gid/lan')   # "giờ" OCR thành "gid"
        self.assertEqual(ds[0]['so_lan_ngay'], [4, 6])

    def test_reversed_range_dropped(self):
        self.assertEqual(lieu('liều 30 - 10 mg/kg mỗi 12 giờ'), [])

    def test_table_fragments_filtered(self):
        self.assertTrue(p._rac('| 10 - 30 sử |" mg/kg mỗi 12 .'))
        self.assertFalse(p._rac('Trẻ em: 10 mg/kg cách 4 - 6 giờ/lần; tối đa 30 mg/kg/24 giờ.'))


@unittest.skipUnless(os.path.exists(documents.chunks_path('DTQGVN-2022-Q2')), 'không có Dược thư trong kho')
class RealBookTests(unittest.TestCase):
    def test_paracetamol_child_dose_present_with_source(self):
        r = p.tra_cuu('Paracetamol 250mg')
        self.assertEqual(r['hoat_chat'], 'PARACETAMOL')
        doses = [(l['mg_kg_min'], l['toi_da_mg_kg_ngay']) for c in r['cau'] for l in c['lieu']]
        self.assertIn((15, 60), doses)       # trẻ 10 - 50 kg: 15 mg/kg, tối đa 60 mg/kg/24 giờ
        self.assertTrue(all(c['citation'] for c in r['cau']))
        self.assertTrue(r['cau'][0]['tre_em'])

    def test_unknown_drug(self):
        self.assertFalse(p.tra_cuu('Augmentin')['nhan_ra'])


if __name__ == '__main__':
    unittest.main()
