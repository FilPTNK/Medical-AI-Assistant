"""Kho bí danh thuốc: bộ gấp chính tả INN, tách biệt dược, lọc bí danh rác."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import drug_alias as da  # noqa: E402

METAS = [
    {'doc_name': 'DTQGVN-2022-Q1', 'generic_name': 'AMOXICILIN', 'intl_name': 'Amoxicillin'},
    {'doc_name': 'DTQGVN-2022-Q1', 'generic_name': 'CEFALEXIN', 'intl_name': 'Cephalexin'},
    {'doc_name': 'DTQGVN-2022-Q1', 'generic_name': 'ASPIRIN', 'intl_name': 'Acetylsalicylic acid',
     'synonyms': 'Acid acetylsalicylic'},
    {'doc_name': 'DTQGVN-2022-Q1', 'generic_name': 'CLORPHENIRAMIN MALEAT',
     'intl_name': 'Chlorpheniramine maleate'},
    {'doc_name': 'DTQGVN-2022-Q2', 'generic_name': 'TIMOLOL MALEAT', 'synonyms': 'THUOC NHO MAT'},
    {'doc_name': 'DTQGVN-2022-Q2', 'generic_name': 'TRAMADOL'},
    {'doc_name': 'DTQGVN-2022-Q2', 'generic_name': 'TRANDOLAPRIL'},
    {'doc_name': 'BD', 'generic_name': 'CARBOCISTEIN',
     'brand_names': 'Mucodyne (Berk, Anh), Rhinathiol (Pháp, Kramer, Lausanne), Lisil (Lenza, Parma, Nhat Bản'},
    # tên hãng dính vào bốn thuốc -> không phải biệt dược
    {'doc_name': 'BD', 'generic_name': 'THUOC A', 'brand_names': 'Sigmatau'},
    {'doc_name': 'BD', 'generic_name': 'THUOC B', 'brand_names': 'Sigmatau'},
    {'doc_name': 'BD', 'generic_name': 'THUOC C', 'brand_names': 'Sigmatau'},
    {'doc_name': 'BD', 'generic_name': 'THUOC D', 'brand_names': 'Sigmatau'},
]
VN = {da._token_key(w) for w in ('nhat', 'ban', 'thuoc', 'nho', 'mat', 'phap')}


def names(store, text):
    return [store.canonical_names(m) for m in store.link(text)]


class InnKeyTests(unittest.TestCase):
    def test_vietnamese_and_international_spellings_meet(self):
        for a, b in [('amoxicillin', 'amoxicilin'), ('cephalexin', 'cefalexin'),
                     ('morphine', 'morphin'), ('cyclosporine', 'ciclosporin'),
                     ('chlorpheniramine', 'clorpheniramin'), ('prednisolone', 'prednisolon'),
                     ('acetylsalicylic acid', 'acid acetylsalicylic'), ('sodium', 'natri')]:
            self.assertEqual(da.inn_key(a), da.inn_key(b), (a, b))

    def test_different_drugs_stay_apart(self):
        self.assertNotEqual(da.inn_key('tramadol'), da.inn_key('trandolapril'))
        self.assertNotEqual(da.inn_key('amoxicilin'), da.inn_key('ampicilin'))


class SplitBrandTests(unittest.TestCase):
    def test_parenthesised_maker_and_lost_close_paren(self):
        got = da.split_brands('Bronchathio (Martin, Phap), Carbocit {C.T, Italia), Lisil (Lenza, Lisomucil (Lirca, ftalia)')
        self.assertEqual(got, ['Bronchathio', 'Carbocit', 'Lisil', 'Lisomucil'])

    def test_salt_derivative_note_is_not_a_brand(self):
        self.assertEqual(da.split_brands('Mucodyne, Dẫn xuất muối lysin'), ['Mucodyne'])


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = da.DrugAliasStore.build(METAS, VN, synonyms_path=None)

    def test_international_name_links_to_vietnamese_monograph(self):
        self.assertEqual(names(self.store, 'liều amoxicillin cho trẻ'), [['Amoxicilin']])
        self.assertEqual(names(self.store, 'cephalexin'), [['Cefalexin']])

    def test_word_order_and_salt_suffix(self):
        self.assertEqual(names(self.store, 'acetylsalicylic acid'), [['Aspirin']])
        self.assertEqual(names(self.store, 'clorpheniramin 4mg'), [['Clorpheniramin Maleat']])

    def test_brand_resolves_to_ingredient(self):
        self.assertEqual(names(self.store, 'Mucodyne cho trẻ'), [['Carbocistein']])
        self.assertEqual(names(self.store, 'rhinathiol'), [['Carbocistein']])

    def test_no_fuzzy_matching(self):
        self.assertEqual(names(self.store, 'tramadol'), [['Tramadol']])
        self.assertEqual(names(self.store, 'tramadolx'), [])

    def test_junk_aliases_are_dropped(self):
        self.assertEqual(names(self.store, 'thuoc nho mat'), [])   # tiêu đề OCR lọt vào "tên khác"
        self.assertEqual(names(self.store, 'nhat ban'), [])        # nước sản xuất
        self.assertEqual(names(self.store, 'sigmatau'), [])        # tên hãng, bốn thuốc

    def test_resolve_name_only_for_non_inn(self):
        self.assertEqual(self.store.resolve_name('Mucodyne 375mg'), 'Carbocistein')
        self.assertIsNone(self.store.resolve_name('Amoxicilin 500mg'))

    def test_with_resolved_name_appends_not_replaces(self):
        da.set_current(self.store)
        try:
            self.assertEqual(da.with_resolved_name('Mucodyne 375mg'), 'Mucodyne 375mg (Carbocistein)')
            self.assertEqual(da.with_resolved_name('Tramadol'), 'Tramadol')
        finally:
            da.set_current(None)

    def test_curated_synonyms_need_approval(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'syn.json'
            path.write_text(json.dumps({'pairs': [
                {'alias': 'Efferalgan', 'canonical': 'Aspirin', 'approved': False},
                {'alias': 'Ecotrin', 'canonical': 'Aspirin', 'approved': True},
            ]}), encoding='utf-8')
            store = da.DrugAliasStore.build(METAS, VN, synonyms_path=str(path))
        self.assertEqual(names(store, 'ecotrin'), [['Aspirin']])
        self.assertEqual(names(store, 'efferalgan'), [])


class ShippedSynonymsTests(unittest.TestCase):
    def test_shipped_file_is_valid(self):
        data = json.loads(Path(da.SYNONYMS_PATH).read_text(encoding='utf-8'))
        for row in data['pairs']:
            self.assertTrue(row['alias'] and row['canonical'] and 'approved' in row, row)


if __name__ == '__main__':
    unittest.main()
