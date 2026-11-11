"""Authenticated Workchat API. A turn is stored only after its result is validated."""

import asyncio
import hashlib
import json
import logging
import os
import sqlite3

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

import config
from workchat import (
    HISTORY_TURNS, MAX_TURN_SECONDS, ThreadCreate, ThreadUpdate, TurnRequest,
    attachment_for, eligible_sources, reply_events, scoped_turn, select_sources, source_list, validate_text,
)
from workchat_store import ChatError, WorkchatStore

log = logging.getLogger(__name__)
PRIVATE = {"Cache-Control": "no-store"}


class PrivateJSON(JSONResponse):
    def __init__(self, *args, headers=None, **kwargs):
        super().__init__(*args, headers={**(headers or {}), **PRIVATE}, **kwargs)


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _http(error):
    return HTTPException(status_code=error.status, detail=str(error), headers=PRIVATE)


def create_router(resolve_actor, search, *, store=None, respond=reply_events):
    router = APIRouter(prefix="/api/workchat", default_response_class=PrivateJSON)
    store = store or WorkchatStore(os.path.join(config.DATA_DIR, "workchat.db"))

    @router.get("/sources")
    def sources(actor: dict = Depends(resolve_actor)):
        return source_list(actor)

    @router.get("/threads")
    def threads(actor: dict = Depends(resolve_actor)):
        return store.list_threads(actor["id"])

    @router.post("/threads", status_code=201)
    def create(payload: ThreadCreate, actor: dict = Depends(resolve_actor)):
        try:
            validate_text(payload.title)
            if payload.specialty:
                validate_text(payload.specialty)
            return store.create(actor["id"], payload.title, payload.specialty)
        except ChatError as error:
            raise _http(error) from None

    @router.delete("/threads", status_code=204, response_class=Response)
    def delete_all(actor: dict = Depends(resolve_actor)):
        try:
            store.change_all(actor["id"], archive=False)
        except ChatError as error:
            raise _http(error) from None
        return Response(status_code=204, headers=PRIVATE)

    @router.post("/archive-all", status_code=204, response_class=Response)
    def archive_all(actor: dict = Depends(resolve_actor)):
        try:
            store.change_all(actor["id"], archive=True)
        except ChatError as error:
            raise _http(error) from None
        return Response(status_code=204, headers=PRIVATE)

    @router.get("/threads/{thread_id}")
    def read(thread_id: str, actor: dict = Depends(resolve_actor)):
        try:
            thread, turns = store.read(actor["id"], thread_id)
        except ChatError as error:
            raise _http(error) from None
        scope = eligible_sources(actor)
        return {**thread, "turns": [scoped_turn(turn, scope, public=True) for turn in turns]}

    @router.patch("/threads/{thread_id}")
    def update(thread_id: str, payload: ThreadUpdate, actor: dict = Depends(resolve_actor)):
        try:
            if payload.title is not None:
                validate_text(payload.title)
            return store.update(actor["id"], thread_id, **payload.model_dump(exclude_none=True))
        except ChatError as error:
            raise _http(error) from None

    @router.delete("/threads/{thread_id}", status_code=204, response_class=Response)
    def delete(thread_id: str, actor: dict = Depends(resolve_actor)):
        try:
            store.delete(actor["id"], thread_id)
        except ChatError as error:
            raise _http(error) from None
        return Response(status_code=204, headers=PRIVATE)

    @router.post("/threads/{thread_id}/turns")
    async def create_turn(
        thread_id: str, payload: TurnRequest, request: Request,
        actor: dict = Depends(resolve_actor), x_deepseek_key: str | None = Header(default=None, max_length=512),
    ):
        owner = actor["id"]
        fingerprint = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
        try:
            validate_text(payload.question)
            thread, _ = await asyncio.to_thread(store.read, owner, thread_id, recent=0)
            if thread["archived"]:
                raise ChatError(409, "Mở lại cuộc trò chuyện đã lưu trữ để gửi câu hỏi.")
            scope = select_sources(actor, payload.doc_names) if payload.mode == "ask" else {}
            if payload.near_page is not None and len(scope) != 1:
                raise ChatError(422, "Chọn một tài liệu để tra theo trang.")
        except ChatError as error:
            raise _http(error) from None

        async def events():
            lease = None
            try:
                # The stream owns the reservation. A disconnect before it starts
                # cannot leave a reservation behind.
                if await request.is_disconnected():
                    return
                lease, existing = store.reserve(owner, thread_id, payload.request_id, fingerprint)
                thread, history = await asyncio.to_thread(store.read, owner, thread_id, recent=HISTORY_TURNS)
                if existing:
                    yield _sse("turn", {"thread": thread,
                                        "turn": scoped_turn(existing, eligible_sources(actor), public=True)})
                    return
                api_key = (x_deepseek_key or "").strip() or config.DEEPSEEK_API_KEY
                async with asyncio.timeout(MAX_TURN_SECONDS):
                    async for kind, data in respond(actor, thread, payload, history, scope, search, api_key):
                        if kind == "status":
                            yield _sse("status", data)
                            continue
                        if await request.is_disconnected():
                            return
                        current = eligible_sources(actor)
                        values = scoped_turn({"reply": data, "attachment": attachment_for(payload, scope)}, current)
                        summary, turn = store.finish(owner, thread_id, lease, payload.request_id, fingerprint,
                                                     payload.question, values)
                        yield _sse("turn", {"thread": summary, "turn": scoped_turn(turn, current, public=True)})
                        return
            except asyncio.CancelledError:
                raise
            except ChatError as error:
                yield _sse("error", {"message": str(error), "status": error.status})
            except TimeoutError:
                yield _sse("error", {"message": "Lượt hỏi mất nhiều thời gian hơn dự kiến. Bạn có thể gửi lại."})
            except Exception as error:
                log.warning("Workchat turn failed (%s)", type(error).__name__)
                yield _sse("error", {"message": "Chưa hoàn tất lượt hỏi. Hãy thử lại."})
            finally:
                try:
                    if lease:
                        store.release(owner, thread_id, lease)
                except sqlite3.Error:
                    log.warning("Workchat lease will expire automatically")

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={**PRIVATE, "X-Accel-Buffering": "no"})

    return router
