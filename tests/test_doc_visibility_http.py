"""Quyền tài liệu ở tầng HTTP: middleware, Thư viện, xoá. Không cần Chroma thật."""
import json
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

    def test_selected_chat_sources_restrict_retrieval_and_keep_visibility_filter(self):
        hidden = {'rieng-b.pdf'}
        hits = main.SearchHits([{'doc_name': 'chung.pdf', 'page_num': 1}])
        with patch.object(main.db, 'search', return_value=hits) as search:
            request = main.QueryRequest(query='câu hỏi', doc_names=['chung.pdf', 'rieng-a.pdf', 'chung.pdf'])
            self.assertEqual(main._retrieve(request.query, request, hidden), hits)
            search.assert_called_once_with(
                request.query, top_k=8, doc_names=['chung.pdf', 'rieng-a.pdf'], exclude_doc_names=hidden,
            )

    def test_no_selected_chat_sources_does_not_fall_back_to_entire_library(self):
        with patch.object(main.db, 'search') as search:
            request = main.QueryRequest(query='câu hỏi', doc_names=[])
            hits = main._retrieve(request.query, request, {'rieng-b.pdf'})
            self.assertEqual(list(hits), [])
            self.assertEqual(hits.status, 'NO_MATCH')
            search.assert_not_called()

    def test_legacy_chat_scope_and_near_page_still_take_precedence(self):
        hits = main.SearchHits([
            {'doc_name': 'chung.pdf', 'page_num': 200},
            {'doc_name': 'chung.pdf', 'page_num': 20},
        ])
        with patch.object(main.db, 'search', return_value=hits) as search:
            request = main.QueryRequest(query='câu hỏi', doc_name='chung.pdf', near_page=20, doc_names=[])
            result = main._retrieve(request.query, request, set())
            self.assertEqual(result[0]['page_num'], 20)
            search.assert_called_once_with(request.query, top_k=8, doc_names=['chung.pdf'], exclude_doc_names=set())

    def test_legacy_chat_without_selection_searches_visible_library(self):
        with patch.object(main.db, 'search', return_value=main.SearchHits()) as search:
            request = main.QueryRequest(query='câu hỏi')
            main._retrieve(request.query, request, {'rieng-b.pdf'})
            search.assert_called_once_with(request.query, top_k=5, exclude_doc_names={'rieng-b.pdf'})

    def test_catalog_import_requires_admin_and_updates_atomically(self):
        record = {
            'id': 'sample', 'name': 'Bản ghi kiểm thử', 'source_title': 'Nguồn kiểm thử',
            'aliases': ['Tên khác'],
            'sections': [{'label': 'Chỉ định', 'text': 'Dòng thứ nhất\nDòng thứ hai'}],
        }
        url = '/api/admin/drug-import?file_format=json'
        admin = {'Authorization': 'Bearer tok-admin'}
        doctor = {'Authorization': 'Bearer tok-a'}
        payload = json.dumps([record])
        with patch.object(main.drug_catalog, 'DB_PATH', Path(self.tmp.name) / 'catalog.db'):
            self.assertEqual(self.client.post(url, content=payload).status_code, 401)
            self.assertEqual(self.client.post(url, headers=doctor, content=payload).status_code, 403)
            self.assertEqual(self.client.post(url, headers=admin, content=payload).json()['count'], 1)
            self.assertEqual(self.get('/api/drug-catalog', 'tok-a').json(), [])
            self.assertEqual(self.client.post(url + '&publish=true', headers=admin, content=payload).status_code, 200)
            endpoint = '/api/drug-catalog/import-sample'
            self.assertEqual(self.get(endpoint, 'tok-a').json()['sections'], record['sections'])
            changed = {**record, 'name': 'Tên cập nhật'}
            invalid = json.dumps([changed, record])
            response = self.client.post(url + '&publish=true', headers=admin, content=invalid)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(self.get(endpoint, 'tok-a').json()['name'], record['name'])
            csv = 'id,name,source_title,indications\r\nsample,Tên cập nhật,Nguồn kiểm thử,"Dòng 1, nguyên văn\r\nDòng 2"'
            response = self.client.post(
                '/api/admin/drug-import?file_format=csv&publish=true', headers=admin,
                content=csv.encode('utf-8-sig'),
            )
            self.assertEqual(response.status_code, 200)
            detail = self.get(endpoint, 'tok-a').json()
            self.assertEqual(detail['name'], 'Tên cập nhật')
            self.assertEqual(detail['sections'][0]['text'], 'Dòng 1, nguyên văn\r\nDòng 2')

    def test_catalog_uses_shared_formulary_chunks_with_printed_page(self):
        chunks_dir = Path(self.tmp.name) / 'chunks'
        chunks_dir.mkdir()
        verified_dir = Path(self.tmp.name) / 'verified'
        verified_dir.mkdir()
        with (
            patch.object(main.drug_catalog, 'DB_PATH', Path(self.tmp.name) / 'catalog.db'),
            patch.object(documents, 'CHUNKS_DIR', str(chunks_dir)),
            patch.object(main.drug_catalog, 'VERIFIED_DIR', verified_dir),
        ):
            for name, visibility in [('volume-1', 'shared'), ('volume-2', 'private')]:
                manifest = documents.new_manifest(
                    name, name, name, 50, doc_series='DTQGVN-2022', parser='dtqg_parser',
                )
                manifest.update(visibility=visibility, owner_id='u-b')
                documents.save_manifest(manifest)
                Path(documents.chunks_path(name)).write_text(json.dumps([{
                    'generic_name': 'PARACETAMOL', 'intl_name': 'Paracetamol, acetaminophen',
                    'synonyms': ['Acetaminophen'], 'field_name': 'Chỉ định',
                    'content': 'Trích đoạn nguyên văn.', 'page_in_file': 101, 'pdf_page': 10,
                }]), encoding='utf-8')
            summaries = self.get('/api/drug-catalog', 'tok-a').json()
            self.assertEqual(len(summaries), 1)
            aliases = [alias.casefold() for alias in summaries[0]['aliases']]
            self.assertEqual(aliases.count('acetaminophen'), 1)
            self.assertNotIn('paracetamol', aliases)
            detail = self.get('/api/drug-catalog/' + summaries[0]['id'], 'tok-a').json()
            self.assertTrue(detail['ocr'])
            self.assertEqual(detail['sections'], [
                {'label': 'Chỉ định', 'page': 101, 'pdf_page': 10, 'text': 'Trích đoạn nguyên văn.'},
            ])
            verified = {
                'name': 'Paracetamol', 'drug_class': '',
                'sections': [{
                    'label': 'Chỉ định',
                    'pages': [{'page': 101, 'pdf_page': 10}, {'page': 102, 'pdf_page': 11}],
                    'blocks': [{'type': 'paragraph', 'text': 'Bản chép đối chiếu.'}],
                }],
            }
            (verified_dir / 'volume-1.json').write_text(json.dumps([verified]), encoding='utf-8')
            self.assertEqual([row['id'] for row in self.get('/api/drug-catalog', 'tok-a').json()],
                             [summaries[0]['id']])
            endpoint = '/api/drug-catalog/' + summaries[0]['id']
            detail = self.get(endpoint, 'tok-a').json()
            self.assertTrue(detail['transcribed'])
            self.assertFalse(detail['ocr'])
            self.assertEqual(detail['sections'], verified['sections'])
            Path(documents.chunks_path('volume-1')).unlink()
            self.assertEqual(self.get(endpoint, 'tok-a').json()['sections'], verified['sections'])

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
