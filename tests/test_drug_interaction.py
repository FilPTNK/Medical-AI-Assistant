"""Đối chiếu tương tác thuốc–thuốc: chạy trên chuyên luận giả, cộng vài cặp trên Dược thư thật nếu có."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import documents  # noqa: E402
import drug_interaction as d  # noqa: E402


def chunk(ten, field, content, atc='', page=10, intl=None):
    return {'generic_name': ten, 'field_name': field, 'content': content, 'atc_code': atc,
            'synonyms': [], 'intl_name': intl, 'page_in_file': page}


FAKE = [
    chunk('WARFARIN NATRI', 'Tương tác thuốc',
          'Các thuốc sau đây khi dùng chung với warfarin có thể làm tăng nguy cơ xuất huyết: '
          'clopidogrel, thuốc chống viêm không steroid (NSAID). Streptokinase bị chống chỉ định.',
          atc='B01AA03', page=1713, intl='Warfarin sodium'),
    chunk('IBUPROFEN', 'Chỉ định', 'Giảm đau, hạ sốt.', atc='C01EB16'),
    chunk('IBUPROFEN', 'Tương tác thuốc', 'Không có tương tác đáng kể với amoxicilin.'),
    chunk('AMOXICILIN', 'Tương tác thuốc', 'Probenecid làm giảm thải trừ amoxicilin qua thận.'),
    chunk('TAMOXIFEN', 'Tương tác thuốc', 'Dùng chung với thuốc chống đông làm tăng tác dụng chống đông.'),
    chunk('STREPTOKINASE', 'Chỉ định', 'Tiêu sợi huyết.'),
]


class FakeIndexTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, 'fake.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(FAKE, f, ensure_ascii=False)
        with patch.object(documents, 'chunks_path', lambda name: path), \
                patch.object(documents, 'display_citation', lambda doc, p: f'Dược thư — tr. {p}'):
            self.idx = d._dung_chi_muc(['fake'])
        p = patch.object(d, '_index', self.idx)
        p.start()
        self.addCleanup(p.stop)
        p2 = patch.object(documents, 'display_citation', lambda doc, p: f'Dược thư — tr. {p}')
        p2.start()
        self.addCleanup(p2.stop)

    def check(self, *names):
        return d.kiem_tra([{'name': n} for n in names])

    def test_group_mention_via_member_list_when_atc_is_wrong(self):
        # ATC của ibuprofen trong kho là C01EB16 — vẫn phải nhận là NSAID.
        r = self.check('Warfarin 5mg', 'Ibuprofen 400mg')
        self.assertEqual(r['ket_luan'], 'co_tuong_tac')
        cap = r['cap'][0]
        self.assertEqual(cap['muc'], 'than_trong')
        bc = cap['bang_chung'][0]
        self.assertEqual((bc['kieu'], bc['khop']), ('nhom', 'NSAID'))
        self.assertEqual(bc['page_num'], 1713)
        self.assertIn('NSAID', bc['cau'])

    def test_contraindication_read_from_sentence(self):
        r = self.check('Warfarin', 'Streptokinase')
        self.assertEqual(r['cap'][0]['muc'], 'chong_chi_dinh')

    def test_negative_sentence_is_not_a_warning(self):
        r = self.check('Ibuprofen', 'Amoxicillin 500mg')   # hai chữ l vẫn nhận ra
        self.assertEqual(r['cap'][0]['muc'], 'khong_tuong_tac')
        self.assertEqual(r['ket_luan'], 'khong_thay')

    def test_token_match_not_substring(self):
        # "tamoxifen" không được coi là amoxicilin.
        r = self.check('Tamoxifen', 'Probenecid')
        self.assertEqual([x['hoat_chat'] for x in r['nhan_ra']], ['TAMOXIFEN'])
        self.assertEqual(r['ket_luan'], 'chua_kiem')

    def test_unrecognised_drugs_are_reported_not_dropped(self):
        r = self.check('Augmentin 1g', 'Warfarin')
        self.assertEqual(r['ket_luan'], 'chua_kiem')
        self.assertEqual([k['ten'] for k in r['khong_nhan_ra']], ['Augmentin 1g'])

    def test_same_drug_twice_is_not_a_pair(self):
        self.assertEqual(self.check('Warfarin 5mg', 'Warfarin natri 2mg')['cap'], [])


@unittest.skipUnless(os.path.exists(documents.chunks_path('DTQGVN-2022-Q2')), 'không có Dược thư trong kho')
class RealBookTests(unittest.TestCase):
    """Cặp kinh điển trên chính Dược thư của kho — chặn hồi quy khi sửa bộ đọc."""

    @classmethod
    def setUpClass(cls):
        d.lam_moi()

    def muc(self, a, b):
        r = d.kiem_tra([{'name': a}, {'name': b}])
        return r['cap'][0]['muc'] if r['cap'] else None

    def test_known_pairs(self):
        self.assertEqual(self.muc('Clarithromycin 500mg', 'Simvastatin 20mg'), 'chong_chi_dinh')
        self.assertEqual(self.muc('Sildenafil', 'Nitroglycerin'), 'chong_chi_dinh')
        self.assertIn(self.muc('Ciprofloxacin', 'Theophylin'), ('tranh', 'chong_chi_dinh'))
        self.assertIn(self.muc('Warfarin', 'Ibuprofen'), ('than_trong', 'tranh', 'chong_chi_dinh'))
        self.assertIsNotNone(self.muc('Tramadol', 'Sertralin'))

    def test_quiet_pairs(self):
        self.assertIsNone(self.muc('Metformin 500mg', 'Amlodipin 5mg'))
        self.assertIsNone(self.muc('Cetirizin', 'Amoxicilin'))


if __name__ == '__main__':
    unittest.main()
