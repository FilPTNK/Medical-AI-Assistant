"""Workchat boundary tests with an isolated SQLite file and synthetic sources."""

import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import workchat
from workchat_routes import create_router
from workchat_store import ChatError, WorkchatStore


def tool_message(name, args):
    return SimpleNamespace(tool_calls=[SimpleNamespace(
        type="function", id="tool_fixture", function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )])


class WorkchatTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = WorkchatStore(Path(tmp.name) / "workchat.db")
        self.manifests = [
            {"doc_name": "approved", "doc_title": "Tài liệu thử nghiệm", "workchat_enabled": True,
             "owner_id": "alice", "visibility": "private", "ingested_at": "version-1", "chunk_count": 1, "pdf_pages": 4},
            {"doc_name": "other", "doc_title": "Kho của tài khoản khác", "workchat_enabled": True,
             "owner_id": "bob", "visibility": "private", "ingested_at": "version-1", "chunk_count": 1},
            {"doc_name": "legacy", "doc_title": "Sách cũ", "ingested_at": "version-1", "chunk_count": 1},
            {"doc_name": "pending", "workchat_enabled": True, "ingested_at": None, "chunk_count": 0},
        ]
        for patcher in (
            patch.object(workchat.documents, "list_manifests", lambda: self.manifests),
            patch.object(workchat.documents, "load_manifest", lambda name: next(
                (m for m in self.manifests if m["doc_name"] == name), None)),
            patch.object(workchat.config, "DEEPSEEK_API_KEY", ""),
            patch.dict(workchat.os.environ, {"WORKCHAT_SOURCE_NAMES": ""}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.search = Mock(return_value=[
            {"doc_name": "other", "page_num": 2, "text": "Nội dung không thuộc phạm vi."},
            {"doc_name": "approved", "page_num": 3, "text": "Nhãn trong ví dụ thử nghiệm: 5 mg."},
        ])
        self.complete = AsyncMock()

        def resolve_actor(request: Request):
            ident = request.headers.get("authorization")
            if ident not in {"Bearer alice", "Bearer bob", "Bearer admin"}:
                raise HTTPException(401)
            owner = ident.split()[-1]
            return {"id": owner, "role": "admin" if owner == "admin" else "doctor",
                    "email": "not-in-model@example.test"}

        def respond(*args):
            return workchat.reply_events(*args, complete=self.complete)

        def resolve_reader(request: Request):
            if request.headers.get("authorization"):
                return resolve_actor(request)
            return {"id": None, "role": "guest"}

        app = FastAPI()
        app.include_router(create_router(
            resolve_actor, self.search, resolve_reader=resolve_reader, store=self.store, respond=respond,
        ))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.base = "/api/workchat/threads"

    def headers(self, owner="alice", model=False):
        return {"Authorization": "Bearer " + owner, **({"X-DeepSeek-Key": "test-provider"} if model else {})}

    def thread(self, owner="alice"):
        response = self.client.post(self.base, headers=self.headers(owner), json={"title": "Sổ tay thử nghiệm"})
        self.assertEqual(response.status_code, 201, response.text)
        return f"{self.base}/{response.json()['id']}"

    def payload(self, **fields):
        return {"request_id": uuid.uuid4().hex, "question": "Câu hỏi thử nghiệm", **fields}

    def turn(self, path, body, owner="alice", model=False):
        return self.client.post(path + "/turns", headers=self.headers(owner, model), json=body)

    def read(self, path, owner="alice"):
        return self.client.get(path, headers=self.headers(owner))

    def reply(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        frames = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
        result = json.loads(frames[-1])
        self.assertIn("turn", result, result)
        return result["turn"]["reply"]

    def stream_error(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertIn("event: error", response.text)
        return json.loads(response.text.split("data: ", 1)[1])

    def test_ownership_and_server_identity(self):
        path = self.thread()
        self.assertEqual(self.client.get(self.base).status_code, 401)
        for other in ("admin", "bob"):
            self.assertEqual(self.read(path, other).status_code, 404)
            self.assertEqual(self.client.patch(path, headers=self.headers(other), json={"pinned": True}).status_code, 404)
            self.assertEqual(self.turn(path, self.payload(), other).status_code, 404)
            self.assertEqual(self.client.delete(path, headers=self.headers(other)).status_code, 404)
        self.assertEqual(self.turn(path, self.payload(owner_id="alice")).status_code, 422)
        self.assertEqual(self.turn(path, self.payload(doc_names=["other"])).status_code, 404)
        self.assertEqual(self.client.get("/api/workchat/sources", headers=self.headers()).json()[0]["doc_name"], "approved")
        self.search.assert_not_called()
        self.complete.assert_not_called()

    def test_guest_reply_uses_visible_sources_without_writing_a_thread(self):
        self.manifests.append({
            "doc_name": "public", "visibility": "shared", "guest_visible": True,
            "workchat_enabled": True, "ingested_at": "version-1", "chunk_count": 1,
        })
        self.search.return_value = [{"doc_name": "public", "page_num": 1, "text": "Đoạn trích thử nghiệm."}]
        self.complete.side_effect = [
            tool_message("search_medical_sources", {"query": "đoạn trích"}),
            SimpleNamespace(content=json.dumps({
                "status": "answered", "paragraphs": [{"text": "Đoạn trích thử nghiệm.", "references": [1]}],
            })),
        ]
        path = "/api/workchat/guest/turns"
        sources = self.client.get("/api/workchat/sources").json()
        self.assertEqual([source["doc_name"] for source in sources], ["public"])
        unavailable = self.client.post(path, json=self.payload(doc_names=["public"]))
        self.assertEqual(unavailable.status_code, 503)
        self.assertIn("DeepSeek", unavailable.json()["detail"])
        self.complete.assert_not_called()
        with patch.object(self.store, "create") as create, patch.object(self.store, "reserve") as reserve:
            with patch.object(workchat.config, "DEEPSEEK_API_KEY", "test-provider"):
                response = self.client.post(path, json=self.payload(
                    doc_names=["public"], previous_questions=["Bối cảnh hỏi trước"],
                ))
            reply = self.reply(response)
            self.assertEqual(reply["kind"], "answer")
            self.assertEqual([source["doc_name"] for source in reply["sources"]], ["public"])
            self.assertIn("Bối cảnh hỏi trước", self.complete.await_args.args[1][1]["content"])
            create.assert_not_called()
            reserve.assert_not_called()
        self.assertEqual(self.client.get(self.base).status_code, 401)
        forbidden = self.client.post(path, headers={"X-DeepSeek-Key": "test-provider"},
                                     json=self.payload(doc_names=["approved"]))
        self.assertEqual(forbidden.status_code, 404)

    def test_empty_corpus_and_outline_work_without_provider(self):
        self.manifests = [manifest for manifest in self.manifests if manifest["doc_name"] != "approved"]
        path = self.thread()
        body = self.payload()
        notice = self.reply(self.turn(path, body, model=True))
        self.assertEqual(notice["sources"], [])
        self.assertIn("Chưa có tài liệu", notice["text"])
        self.assertEqual(self.reply(self.turn(path, body)), notice)
        outline = self.reply(self.turn(path, self.payload(mode="consult_outline")))
        self.assertEqual(outline["kind"], "outline")
        self.assertEqual(outline["outline"]["sections"][0], "Câu hỏi cần hội chẩn")
        turns = self.read(path).json()["turns"]
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[1]["reply"], outline)
        self.assertEqual(self.stream_error(self.turn(path, {**body, "question": "Nội dung khác"}))["status"], 409)
        self.search.assert_not_called()
        self.complete.assert_not_called()

    def test_tool_arguments_history_citations_and_source_revocation(self):
        path = self.thread()
        self.reply(self.turn(path, self.payload(question="Bối cảnh thử nghiệm trước")))
        self.complete.side_effect = [
            tool_message("search_medical_sources", {"query": 123}),
            tool_message("search_medical_sources", {"query": "nhãn ví dụ"}),
            SimpleNamespace(content=json.dumps({
                "status": "answered", "paragraphs": [{"text": "Nhãn ví dụ ghi 5 mg.", "references": [1]}],
            })),
        ]
        reply = self.reply(self.turn(path, self.payload(doc_names=["approved"], near_page=3), model=True))
        self.assertEqual(reply["kind"], "answer")
        self.assertEqual([source["doc_name"] for source in reply["sources"]], ["approved"])
        self.assertEqual(reply["paragraphs"][0]["references"], [1])
        self.search.assert_called_once_with("nhãn ví dụ", ("approved",))
        self.assertEqual(self.complete.await_count, 3)
        final = self.complete.await_args.args[1]
        self.assertTrue(any(message["content"] == "Bối cảnh thử nghiệm trước" for message in final))
        self.assertNotIn("not-in-model", str(final))
        self.assertNotIn("Nội dung không thuộc phạm vi", str(final))
        self.assertEqual(final[-1]["tool_call_id"], final[-2]["tool_calls"][0]["id"])
        self.manifests[0]["ingested_at"] = "version-2"
        turn = self.read(path).json()["turns"][-1]
        self.assertEqual(turn["reply"]["kind"], "notice")
        self.assertEqual(turn["reply"]["sources"], [])
        self.assertIsNone(turn["attachment"])
        self.assertNotIn("5 mg", str(turn))

    def test_selected_source_without_key_returns_real_excerpts(self):
        path = self.thread()
        reply = self.reply(self.turn(path, self.payload(doc_names=["approved"])))
        self.assertEqual(reply["kind"], "notice")
        self.assertIn("Thêm khóa DeepSeek", reply["text"])
        self.assertEqual([(source["doc_name"], source["page_num"]) for source in reply["sources"]], [("approved", 3)])
        self.complete.assert_not_called()

    def test_wrong_citations_and_units_do_not_become_answers(self):
        path = self.thread()
        for refs, text in (([2], "Nhãn ví dụ ghi 5 mg."), ([1], "Nhãn ví dụ ghi 5 g.")):
            self.complete.side_effect = [
                tool_message("search_medical_sources", {"query": "nhãn ví dụ"}),
                SimpleNamespace(content=json.dumps({
                    "status": "answered", "paragraphs": [{"text": text, "references": refs}],
                })),
            ]
            reply = self.reply(self.turn(path, self.payload(doc_names=["approved"]), model=True))
            self.assertEqual(reply["kind"], "notice")
            self.assertEqual(len(reply["sources"]), 1)
            self.assertNotIn("paragraphs", reply)

    def test_lease_and_bulk_operations_are_account_scoped(self):
        path = self.thread()
        other_path = self.thread()
        bob_path = self.thread("bob")
        thread_id = path.rsplit("/", 1)[-1]
        lease, _ = self.store.reserve("alice", thread_id, "request-1", "fingerprint")
        self.assertEqual(self.stream_error(self.turn(other_path, self.payload()))["status"], 409)
        self.assertEqual(self.client.delete(self.base, headers=self.headers()).status_code, 409)
        self.store.release("alice", thread_id, lease)
        self.assertEqual(self.client.post("/api/workchat/archive-all", headers=self.headers()).status_code, 204)
        self.assertTrue(self.read(path).json()["archived"])
        self.assertEqual(self.turn(other_path, self.payload()).status_code, 409)
        self.assertFalse(self.read(bob_path, "bob").json()["archived"])
        self.assertEqual(self.client.delete(self.base, headers=self.headers()).status_code, 204)
        self.assertEqual(self.read(path).status_code, 404)
        self.assertEqual(self.read(bob_path, "bob").status_code, 200)
        with self.assertRaises(ChatError):
            self.store.reserve("alice", thread_id, "request-2", "fingerprint")


if __name__ == "__main__":
    unittest.main()
