"""Tài liệu tự tải là kho riêng của từng tài khoản; tài liệu quản trị tải là kho chung."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import documents  # noqa: E402

ADMIN = {'id': 'u-admin', 'role': 'admin'}
DOC_A = {'id': 'u-a', 'role': 'doctor'}
DOC_B = {'id': 'u-b', 'role': 'doctor'}


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(documents, 'DOCUMENTS_DIR', self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)

        def save(name, **fields):
            m = documents.new_manifest(name, name, name, 1, parser='generic')
            m.update(fields)
            documents.save_manifest(m)

        save('sach-tham-khao')                                   # bản cũ, không có visibility
        save('chung.pdf', owner_id='u-admin', visibility='shared')
        save('rieng-a.pdf', owner_id='u-a', visibility='private')
        save('rieng-b.pdf', owner_id='u-b', visibility='private')

    def test_private_doc_only_visible_to_owner(self):
        self.assertTrue(documents.can_view(DOC_A, 'rieng-a.pdf'))
        self.assertFalse(documents.can_view(DOC_B, 'rieng-a.pdf'))
        # Quản trị cũng không thấy kho riêng của bác sĩ.
        self.assertFalse(documents.can_view(ADMIN, 'rieng-a.pdf'))
        self.assertFalse(documents.can_view(None, 'rieng-a.pdf'))

    def test_shared_and_legacy_docs_visible_to_everyone(self):
        for user in (ADMIN, DOC_A, DOC_B):
            self.assertTrue(documents.can_view(user, 'chung.pdf'))
            self.assertTrue(documents.can_view(user, 'sach-tham-khao'))
            # Không có manifest (vd. tên gõ bừa) thì không chặn ở đây — route tự trả 404.
            self.assertTrue(documents.can_view(user, 'khong-ton-tai'))

    def test_delete_rules(self):
        self.assertTrue(documents.can_delete(DOC_A, 'rieng-a.pdf'))
        self.assertFalse(documents.can_delete(DOC_B, 'rieng-a.pdf'))
        self.assertFalse(documents.can_delete(ADMIN, 'rieng-a.pdf'))
        self.assertTrue(documents.can_delete(ADMIN, 'chung.pdf'))
        self.assertTrue(documents.can_delete(ADMIN, 'sach-tham-khao'))
        self.assertFalse(documents.can_delete(DOC_A, 'chung.pdf'))
        self.assertFalse(documents.can_delete(DOC_A, 'sach-tham-khao'))

    def test_hidden_doc_names_is_everyone_elses_private_docs(self):
        self.assertEqual(documents.hidden_doc_names(DOC_A), {'rieng-b.pdf'})
        self.assertEqual(documents.hidden_doc_names(DOC_B), {'rieng-a.pdf'})
        self.assertEqual(documents.hidden_doc_names(ADMIN), {'rieng-a.pdf', 'rieng-b.pdf'})


if __name__ == '__main__':
    unittest.main()
