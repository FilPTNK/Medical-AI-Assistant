"""Lịch sử tra cứu, tô sáng, ghi chú tài liệu là của từng tài khoản."""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import library_db  # noqa: E402

HL = {'page_num': 3, 'quote': 'liều 500 mg', 'start_offset': 0, 'end_offset': 10}


class OwnerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # Windows: sqlite3 giữ khoá tệp tới khi GC
        self.addCleanup(tmp.cleanup)
        p = patch.object(library_db, 'DB_PATH', os.path.join(tmp.name, 'library.db'))
        p.start()
        self.addCleanup(p.stop)
        library_db.init_db()

    def test_history_is_per_owner(self):
        a = library_db.add_history('u-a', 'paracetamol cho bệnh nhân Nguyễn Văn A', 'tl', [])
        library_db.add_history('u-b', 'ibuprofen', 'tl', [])
        self.assertEqual([r['query'] for r in library_db.list_history('u-b')], ['ibuprofen'])
        self.assertIsNone(library_db.get_history('u-b', a['id']))
        self.assertFalse(library_db.delete_history('u-b', a['id']))
        self.assertEqual(library_db.list_history('u-b', 'paracetamol'), [])
        self.assertEqual(library_db.find_similar_questions('u-b', 'paracetamol cho bệnh nhân Nguyễn Văn A'), [])
        self.assertEqual(len(library_db.find_similar_questions('u-a', 'paracetamol cho bệnh nhân Nguyễn Văn A')), 1)
        self.assertNotIn('owner_id', a)

    def test_clear_history_only_clears_own(self):
        library_db.add_history('u-a', 'q1', 'tl', [])
        library_db.add_history('u-b', 'q2', 'tl', [])
        library_db.clear_history('u-a')
        self.assertEqual(library_db.list_history('u-a'), [])
        self.assertEqual(len(library_db.list_history('u-b')), 1)

    def test_highlights_are_per_owner(self):
        h = library_db.create_highlight('u-a', 'sach', HL)
        self.assertEqual(library_db.list_highlights('u-b'), [])
        self.assertEqual(library_db.search_highlights('u-b', '500'), [])
        self.assertEqual(library_db.count_highlights_by_document('u-b'), {})
        self.assertEqual(library_db.count_highlights_by_document('u-a'), {'sach': 1})
        self.assertIsNone(library_db.update_highlight('u-b', h['id'], {'note': 'sửa trộm'}))
        self.assertFalse(library_db.delete_highlight('u-b', h['id']))
        self.assertIsNone(library_db.get_highlight('u-a', h['id'])['note'])
        self.assertEqual(library_db.update_highlight('u-a', h['id'], {'note': 'ok'})['note'], 'ok')

    def test_doc_notes_are_per_owner(self):
        library_db.save_doc_note('u-a', 'sach', 'ghi chú của A', 'BS A')
        self.assertEqual(library_db.get_doc_note('u-b', 'sach')['content'], '')
        library_db.save_doc_note('u-b', 'sach', 'ghi chú của B', 'BS B')
        self.assertEqual(library_db.get_doc_note('u-a', 'sach')['content'], 'ghi chú của A')
        library_db.delete_highlights_for_document('sach')
        self.assertEqual(library_db.get_doc_note('u-a', 'sach')['content'], '')

    def test_legacy_rows_assigned_once_by_unique_name(self):
        with sqlite3.connect(library_db.DB_PATH) as conn:
            for i, who in enumerate(['BS A', 'BS A', None, 'smoke']):
                conn.execute("INSERT INTO search_history (id, query, created_by, created_at) VALUES (?, ?, ?, ?)",
                             (f'old{i}', f'cũ {i}', who, f'2026-09-0{i + 1}'))
            conn.execute("INSERT INTO doc_notes (doc_name, content, updated_by, updated_at) VALUES "
                         "('sach', 'ghi chú cũ', 'BS A', '2026-09-01')")
        counts = library_db.assign_legacy_owners({'BS A': 'u-a'})
        self.assertEqual(counts['search_history'], 2)
        self.assertEqual(counts['doc_notes'], 1)
        self.assertEqual(len(library_db.list_history('u-a')), 2)
        self.assertEqual(library_db.get_doc_note('u-a', 'sach')['content'], 'ghi chú cũ')
        # Lần sau không chạy nữa: tài khoản mới tên "smoke" không nhận dòng mồ côi.
        self.assertEqual(library_db.assign_legacy_owners({'smoke': 'u-new'}), {})
        self.assertEqual(library_db.list_history('u-new'), [])


if __name__ == '__main__':
    unittest.main()
