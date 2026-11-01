"""Quyền tài liệu ở tầng HTTP: middleware, Thư viện, xoá. Không cần Chroma thật."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from fastapi.testclient import TestClient  # noqa: E402

USERS = {
    'tok-admin': {'id': 'u-admin', 'role': 'admin', 'display_name': 'Quản trị'},
    'tok-a': {'id': 'u-a', 'role': 'doctor', 'display_name': 'BS A'},
    'tok-b': {'id': 'u-b', 'role': 'doctor', 'display_name': 'BS B'},
}


class HttpVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import ở đây chứ không ở đầu tệp: test_wp1/test_wp3 thay module giả vào
        # sys.modules, nên main thật (kéo theo vector_store, generic_ingest...)
        # không được nằm lại sau khi lớp này chạy xong.
        cls._before = set(sys.modules)
        global documents, main
        import documents
        import main

    @classmethod
    def tearDownClass(cls):
        for name in set(sys.modules) - cls._before:
            sys.modules.pop(name, None)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (
            patch.object(documents, 'DOCUMENTS_DIR', self.tmp.name),
            patch.object(main.auth_db, 'resolve_session', lambda tok: USERS.get(tok)),
            patch.object(main.db, 'list_documents', lambda: [
                {'doc_name': n, 'page_count': 1, 'chunk_count': 1}
                for n in ('chung.pdf', 'rieng-a.pdf', 'rieng-b.pdf')]),
            patch.object(main.db, 'delete_document', lambda name: None),
            patch.object(main.library_db, 'delete_highlights_for_document', lambda name: None),
        ):
            p.start()
            self.addCleanup(p.stop)
        for name, owner, vis in (('chung.pdf', 'u-admin', 'shared'),
                                 ('rieng-a.pdf', 'u-a', 'private'),
                                 ('rieng-b.pdf', 'u-b', 'private')):
            m = documents.new_manifest(name, name, name, 1, parser='generic')
            m.update(owner_id=owner, visibility=vis)
            documents.save_manifest(m)
        self.client = TestClient(main.app)

    def get(self, path, tok):
        return self.client.get(path, headers={'Authorization': f'Bearer {tok}'})

    def delete(self, path, tok):
        return self.client.delete(path, headers={'Authorization': f'Bearer {tok}'})

    def test_library_lists_only_visible_docs(self):
        names = {d['doc_name']: d for d in self.get('/api/documents', 'tok-a').json()}
        self.assertEqual(set(names), {'chung.pdf', 'rieng-a.pdf'})
        self.assertTrue(names['rieng-a.pdf']['can_delete'])
        self.assertFalse(names['chung.pdf']['can_delete'])
        self.assertEqual(names['rieng-a.pdf']['visibility'], 'private')
        admin = {d['doc_name']: d for d in self.get('/api/documents', 'tok-admin').json()}
        self.assertEqual(set(admin), {'chung.pdf'})
        self.assertTrue(admin['chung.pdf']['can_delete'])

    def test_other_doctors_private_doc_is_404_everywhere(self):
        for path in ('/api/documents/rieng-b.pdf/pages/1',
                     '/api/documents/rieng-b.pdf/highlights',
                     '/api/documents/rieng-b.pdf/note',
                     '/api/documents/rieng-b.pdf/search?q=abc'):
            self.assertEqual(self.get(path, 'tok-a').status_code, 404, path)
        self.assertEqual(self.client.post('/api/documents/rieng-b.pdf/download-ticket',
                                          headers={'Authorization': 'Bearer tok-a'}).status_code, 404)
        self.assertEqual(self.delete('/api/documents/rieng-b.pdf', 'tok-a').status_code, 404)

    def test_delete_rules(self):
        self.assertEqual(self.delete('/api/documents/chung.pdf', 'tok-a').status_code, 403)
        self.assertEqual(self.delete('/api/documents/rieng-a.pdf', 'tok-a').status_code, 200)
        self.assertEqual(self.delete('/api/documents/chung.pdf', 'tok-admin').status_code, 200)

    def test_history_highlights_notes_are_per_account(self):
        lib_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(lib_tmp.cleanup)
        p = patch.object(main.library_db, 'DB_PATH', os.path.join(lib_tmp.name, 'library.db'))
        p.start()
        self.addCleanup(p.stop)
        main.library_db.init_db()
        main.library_db.add_history('u-a', 'bệnh nhân Trần B dùng warfarin', 'tl', [])
        auth = lambda tok: {'Authorization': f'Bearer {tok}'}

        # Body giả danh người khác: máy chủ bỏ qua, gắn theo phiên đăng nhập.
        h = self.client.post('/api/documents/chung.pdf/highlights', headers=auth('tok-a'), json={
            'page_num': 1, 'quote': 'liều', 'start_offset': 0, 'end_offset': 4, 'created_by': 'BS B'}).json()
        self.assertEqual(h['created_by'], 'BS A')
        self.client.put('/api/documents/chung.pdf/note', headers=auth('tok-a'),
                        json={'content': 'ghi chú riêng của A', 'updated_by': 'BS B'})

        self.assertEqual(self.get('/api/search-history', 'tok-b').json(), [])
        self.assertEqual(len(self.get('/api/search-history', 'tok-a').json()), 1)
        self.assertEqual(self.get('/api/highlights', 'tok-b').json(), [])
        self.assertEqual(self.get('/api/highlights/counts', 'tok-b').json(), {})
        self.assertEqual(self.get('/api/documents/chung.pdf/highlights', 'tok-b').json(), [])
        self.assertEqual(self.get('/api/documents/chung.pdf/note', 'tok-b').json()['content'], '')
        self.assertEqual(self.client.patch(f"/api/highlights/{h['id']}", headers=auth('tok-b'),
                                           json={'note': 'x'}).status_code, 404)
        self.assertEqual(self.delete(f"/api/highlights/{h['id']}", 'tok-b').status_code, 404)
        self.assertEqual(self.delete('/api/search-history', 'tok-b').status_code, 200)
        self.assertEqual(len(self.get('/api/search-history', 'tok-a').json()), 1)


if __name__ == '__main__':
    unittest.main()
