"""WP3: mock PDF/OCR/ingest, không cần thư viện nặng hay dữ liệu bệnh nhân."""
import importlib
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

BACKEND = str(Path(__file__).resolve().parents[1] / "backend")


class FakePage:
    def __init__(self, text):
        self.text = text
        self.rect = types.SimpleNamespace(width=595, height=842)

    def get_text(self):
        return self.text


class FakePdf:
    def __init__(self, pages):
        self.pages = [FakePage(t) for t in pages]
        self.is_pdf = True
        self.needs_pass = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, idx):
        return self.pages[idx]


class WP3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, BACKEND)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.documents = types.SimpleNamespace(
            safe_doc_name=lambda name: os.path.basename(name),
            list_manifests=lambda: [],
            upload_path=lambda name: str(Path(cls.tmp.name) / name),
            manifest_path=lambda name: str(Path(cls.tmp.name) / (name + ".json")),
            pages_cache_path=lambda name: str(Path(cls.tmp.name) / (name + ".pages")),
            chunks_path=lambda name: str(Path(cls.tmp.name) / (name + ".chunks")),
            page_map_path=lambda name: str(Path(cls.tmp.name) / (name + ".map")),
            ocr_dir=lambda name: str(Path(cls.tmp.name) / (name + ".ocr")),
            page_images_dir=lambda name: str(Path(cls.tmp.name) / (name + ".images")),
            ocr_page_path=lambda name, n: str(Path(cls.tmp.name) / f"{name}.{n}.txt"),
        )
        cls.pages = ["a" * 50, "scan", "b" * 60]
        cls.ocr = mock.Mock(side_effect=lambda path, idx, name, dpi, col, lang:
                            Path(cls.documents.ocr_page_path(name, idx + 1)).write_text("Văn bản được nhận dạng", encoding="utf-8"))
        cls.mods = {
            "config": types.SimpleNamespace(UPLOAD_DIR=cls.tmp.name),
            "documents": cls.documents,
            "ingest_book": types.SimpleNamespace(ingest=mock.Mock()),
            "ocr_book": types.SimpleNamespace(ocr_page=cls.ocr),
            "dtqg_parser": types.SimpleNamespace(split_long=lambda text: [text[i:i + 10] for i in range(0, len(text), 10)]),
            "pymupdf": types.SimpleNamespace(open=lambda path: FakePdf(cls.pages)),
        }
        cls.patch = mock.patch.dict(sys.modules, cls.mods)
        cls.patch.start()
        cls.g = importlib.import_module("generic_ingest")
        cls.jobs = importlib.import_module("ingest_jobs")

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        sys.modules.pop("generic_ingest", None)
        sys.modules.pop("ingest_jobs", None)
        cls.tmp.cleanup()
        sys.path.remove(BACKEND)

    def test_ocr_only_short_page_and_warning(self):
        path = Path(self.tmp.name) / "sample.pdf"
        path.write_bytes(b"%PDF-123")
        pages, count, ocr_count = self.g.iter_page_texts(str(path), "sample.pdf")
        self.assertEqual((count, ocr_count), (3, 1))
        self.assertEqual(pages[1], "a" * 50)
        self.assertIn("Văn bản", pages[2])
        self.assertEqual(self.ocr.call_count, 1)
        self.assertTrue(self.g.low_quality_ocr("?@#$"))
        self.assertEqual(self.g.chunk_generic_pages({2: "a" * 21})[0]["page_in_file"], 2)

    def test_pdf_signature_pages_password(self):
        path = Path(self.tmp.name) / "bad.pdf"
        path.write_bytes(b"FAKE!")
        with self.assertRaises(ValueError):
            self.g.validate_pdf(str(path))
        path.write_bytes(b"%PDF-123")
        self.assertEqual(self.g.validate_pdf(str(path)), 3)
        with mock.patch.object(self.g.fitz, "open", return_value=FakePdf(["x"] * 301)):
            with self.assertRaises(ValueError):
                self.g.validate_pdf(str(path))
        secret = FakePdf(["x"])
        secret.needs_pass = True
        with mock.patch.object(self.g.fitz, "open", return_value=secret):
            with self.assertRaises(ValueError):
                self.g.validate_pdf(str(path))

    def test_name_casefold_windows_separator_and_length(self):
        name = self.g.slugify_doc_name("folder\\ÄBC.pdf", {"äbc.pdf"})
        self.assertEqual(name, "ÄBC (2).pdf")
        self.assertLessEqual(len(self.g.slugify_doc_name("z" * 500 + ".pdf")), 120)

    def test_queue_serial_and_capacity(self):
        jobs = self.jobs
        with mock.patch.dict(jobs._jobs, {}, clear=True):
            three = [jobs.reserve(str(i), lambda active, i=i: f"{i}.pdf") for i in range(3)]
            with self.assertRaises(ValueError):
                jobs.reserve("overflow", lambda active: "overflow.pdf")
            seen = []
            done = threading.Event()
            for index, job in enumerate(three):
                def task(i=index, j=job["job_id"]):
                    seen.append(i)
                    jobs.update(j, status="done")
                    if i == 2:
                        done.set()
                jobs.submit(job["job_id"], task)
            self.assertTrue(done.wait(2))
            self.assertEqual(seen, [0, 1, 2])
            self.assertFalse(jobs.is_active("0.pdf"))

    def test_pipeline_preserves_chunk_schema_and_reports_warning(self):
        doc = self.documents
        name = "pipeline.pdf"
        Path(doc.upload_path(name)).write_bytes(b"%PDF-")
        warnings = []
        with mock.patch.object(doc, "new_manifest", create=True, return_value={"doc_name": name}), \
             mock.patch.object(doc, "save_manifest", create=True) as save, \
             mock.patch.object(self.g, "validate_pdf", return_value=2), \
             mock.patch.object(self.g, "iter_page_texts", return_value=({1: "Một câu đủ dài để đọc rõ nội dung tài liệu trên trang.", 2: "???"}, 2, 1)):
            result = self.g.ingest_generic_pdf(name, doc.upload_path(name), "Tài liệu",
                                                warning_cb=warnings.append, uploaded_by="Bác sĩ A")
        self.assertEqual(result["pages"], 2)
        self.assertIn(2, warnings)
        self.assertEqual(save.call_args.args[0]["uploaded_by"], "Bác sĩ A")
        import json
        chunks = json.loads(Path(doc.chunks_path(name)).read_text(encoding="utf-8"))
        self.assertTrue(chunks)
        self.assertEqual(set(chunks[0]), {"chunk_id", "field_name", "content", "page_in_file", "pdf_page"})
        self.mods["ingest_book"].ingest.assert_called()

    def test_large_page_reduces_dpi(self):
        rect = types.SimpleNamespace(width=1190, height=1684)
        self.assertLess(self.g.ocr_dpi_for_page(rect), 300)
        self.assertLessEqual(self.g.ocr_dpi_for_page(rect), 250)

    def test_cleanup_failure_keeps_source_for_retry(self):
        doc = self.documents
        name = "retry.pdf"
        Path(doc.manifest_path(name)).write_text("{}")
        Path(doc.upload_path(name)).write_bytes(b"%PDF-")
        failed_db = types.SimpleNamespace(delete_document=mock.Mock(side_effect=RuntimeError("index locked")))
        with mock.patch.object(doc, "list_manifests", return_value=[
            {"doc_name": name, "parser": "generic", "ingested_at": None}
        ]):
            with self.assertRaises(RuntimeError):
                self.g.cleanup_orphans(failed_db)
        self.assertTrue(Path(doc.manifest_path(name)).exists())
        self.assertTrue(Path(doc.upload_path(name)).exists())

    def test_orphan_cleanup_only_incomplete_generic(self):
        doc = self.documents
        fake_db = types.SimpleNamespace(delete_document=mock.Mock())
        names = ["unfinished.pdf", "complete.pdf", "reference.pdf"]
        manifests = [{"doc_name": names[0], "parser": "generic", "ingested_at": None},
                     {"doc_name": names[1], "parser": "generic", "ingested_at": "now"},
                     {"doc_name": names[2], "parser": "dtqg", "ingested_at": None}]
        for name in names:
            Path(doc.manifest_path(name)).write_text("{}")
            Path(doc.upload_path(name)).write_bytes(b"%PDF-")
        with mock.patch.object(doc, "list_manifests", return_value=manifests):
            self.g.cleanup_orphans(fake_db)
        fake_db.delete_document.assert_called_once_with(names[0])
        self.assertFalse(Path(doc.upload_path(names[0])).exists())
        self.assertTrue(Path(doc.upload_path(names[1])).exists())
        self.assertTrue(Path(doc.upload_path(names[2])).exists())


if __name__ == "__main__":
    unittest.main()
