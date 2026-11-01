"""Ý định -> mục chuyên luận, khe điều kiện bệnh nhân, viết tắt đã duyệt."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import query_intent as qi  # noqa: E402


def u(q):
    return qi.understand(q)


class IntentTests(unittest.TestCase):
    def test_one_intent_one_section(self):
        cases = {
            'liều dùng paracetamol': ('dosage', {'DOSAGE'}),
            'chống chỉ định của metformin': ('contraindication', {'CONTRAINDICATION'}),
            'tác dụng phụ của ibuprofen': ('adr', {'ADR', 'ADR_MANAGEMENT'}),
            'warfarin tương tác với thuốc nào': ('interaction', {'INTERACTION', 'INCOMPATIBILITY'}),
            'cefalexin cho con bú': ('lactation', {'LACTATION'}),
            'dosage of amoxicillin': ('dosage', {'DOSAGE'}),
        }
        for q, (intent, sections) in cases.items():
            r = u(q)
            self.assertEqual(r.intents, [intent], q)
            self.assertEqual(r.sections, sections, q)

    def test_longer_phrase_wins(self):
        # "quá liều" không để lại "liều"; "chống chỉ định" không để lại "chỉ định";
        # "tác dụng phụ" không để lại "tác dụng".
        self.assertEqual(u('quá liều paracetamol').intents, ['overdose'])
        self.assertEqual(u('chống chỉ định aspirin').intents, ['contraindication'])
        self.assertEqual(u('tác dụng phụ của morphin').intents, ['adr'])

    def test_asking_which_drug_is_indications(self):
        self.assertEqual(u('thuốc hạ sốt').intents, ['indications'])
        self.assertEqual(u('trẻ em bị tiêu chảy dùng thuốc nào').intents, ['indications'])

    def test_no_intent_no_sections(self):
        r = u('paracetamol')
        self.assertTrue(r.empty)
        self.assertEqual(r.sections, set())


class SlotTests(unittest.TestCase):
    def test_conditional_question(self):
        r = u('liều amoxicillin cho trẻ 15 kg suy thận')
        self.assertEqual(r.intents, ['dosage'])
        self.assertEqual(r.slots, ['child', 'renal'])
        self.assertEqual(r.weight, '15 kg')
        # có ý định rõ thì khe không thêm mục nào
        self.assertEqual(r.sections, {'DOSAGE'})

    def test_age_sets_population(self):
        self.assertIn('child', u('paracetamol cho bé 3 tuổi').slots)
        self.assertIn('elderly', u('bệnh nhân 70 tuổi dùng digoxin').slots)
        self.assertIn('child', u('trẻ 6 tháng tuổi bị sốt').slots)

    def test_slot_only_question_points_to_sections(self):
        r = u('người cao tuổi dùng diazepam')
        self.assertEqual(r.intents, [])
        self.assertEqual(r.sections, {'DOSAGE', 'WARNINGS'})

    def test_polarity(self):
        r = u('amoxicilin có dùng được cho bà bầu không')
        self.assertTrue(r.polarity)
        self.assertEqual(r.intents, ['pregnancy'])
        self.assertEqual(r.labels(), ['Thời kỳ mang thai'])


class SectionOfTests(unittest.TestCase):
    def test_biet_duoc_interaction_lives_under_warnings(self):
        meta = {'field_type': 'WARNINGS', 'field_name': 'Tương tác thuốc'}
        self.assertEqual(qi.section_of(meta), 'INTERACTION')
        self.assertEqual(qi.section_of({'field_type': 'WARNINGS', 'field_name': 'Thận trọng'}), 'WARNINGS')


class AbbreviationTests(unittest.TestCase):
    def test_uppercase_abbreviation_expands(self):
        self.assertEqual(qi.expand_abbreviations('metformin cho bệnh nhân ĐTĐ'), [('ĐTĐ', 'đái tháo đường')])
        self.assertEqual(qi.expand_abbreviations('thuốc THA'), [('THA', 'tăng huyết áp')])

    def test_short_lowercase_is_a_syllable_not_an_abbreviation(self):
        self.assertEqual(qi.expand_abbreviations('tha thứ'), [])

    def test_unapproved_is_ignored(self):
        self.assertEqual(qi.expand_abbreviations('HC thận hư'), [])


if __name__ == '__main__':
    unittest.main()
