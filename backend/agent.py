import json
from typing import Any, Callable, Dict, List, Optional
import config
import patient_context
from llm_client import _strip_json_fences, _llm_client

# 3 rounds of tool use max, then one forced final round with no tools.
MAX_AGENT_STEPS = 4

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "tra_cuu_duoc_thu",
            "description": (
                "Tra cứu Dược Thư Quốc Gia Việt Nam và tài liệu y văn đã số hóa để kiểm chứng "
                "một giả thuyết chẩn đoán, tiêu chuẩn lâm sàng, hoặc thông tin thuốc bằng tài liệu gốc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Từ khóa tra cứu: tên bệnh, hội chứng, triệu chứng đặc hiệu hoặc tên thuốc."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "xem_tien_su_benh_nhan",
            "description": (
                "Lấy tiền sử bệnh án của bệnh nhân hiện tại: dị ứng, bệnh nền, các lần khám trước, "
                "chẩn đoán cũ, sinh hiệu và ghi chú lâm sàng gần đây."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    }
]


def _summarize_patient_history(patient_id: str) -> str:
    """
    Tiền sử đã khử danh. Định nghĩa thật nằm ở patient_context — cả đường agent
    này lẫn cây chẩn đoán bốn bước đều gọi cùng một hàm, để không có hai phiên
    bản "tiền sử bệnh nhân" trôi khác nhau.

    Trước đây hàm này tự dựng chuỗi và mở đầu bằng ĐÚNG TÊN bệnh nhân, nên tên
    đi thẳng ra DeepSeek mỗi lần agent gọi tool.
    """
    context = patient_context.build_patient_context(patient_id)
    if context is None:
        return "Không tìm thấy hồ sơ bệnh nhân."
    return context


def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    text = text or ""
    try:
        return json.loads(_strip_json_fences(text))
    except (TypeError, ValueError):
        pass
    # The model sometimes stops calling tools on its own (before the forced-final step where
    # response_format=json_object applies) and prefaces the JSON with free-text reasoning —
    # tools and response_format can't be combined in the same call, so fall back to pulling
    # the JSON object out of wherever it landed in the message.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except (TypeError, ValueError):
            return None
    return None


def _parse_final_answer(content: str, trace: List[Dict[str, Any]], sources_used: List[Dict[str, Any]],
                        patient_ctx: Optional[str] = None) -> Dict[str, Any]:
    parsed = _safe_json_loads(content) or {}
    differentials = parsed.get("diagnosis_differentials") or []
    if not isinstance(differentials, list):
        differentials = []
    return {
        "diagnosis_primary": str(parsed.get("diagnosis_primary") or "").strip(),
        "diagnosis_differentials": [str(d).strip() for d in differentials if str(d).strip()],
        "reasoning": str(parsed.get("reasoning") or content or "").strip(),
        "agent_trace": trace,
        "agent_sources": sources_used,
        # Đúng chuỗi tiền sử đã gửi đi, trả ngược về cho giao diện hiện ra.
        "patient_context": patient_ctx,
    }


def run_diagnostic_agent(
    patient_id: str,
    symptoms: str,
    search_literature_fn: Callable[[str], List[Dict[str, Any]]],
    custom_api_key: str = "",
) -> Dict[str, Any]:
    """
    Multi-step ReAct-style diagnostic agent. Unlike a one-shot LLM call, the model itself
    decides whether it needs to call `xem_tien_su_benh_nhan` (patient history) and/or
    `tra_cuu_duoc_thu` (RAG search over the Dược Thư Quốc Gia) before committing to a
    diagnosis, and every tool call it makes is recorded in `agent_trace` so the doctor can
    see the reasoning path, not just the final answer.
    """
    api_key = custom_api_key if custom_api_key else config.DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError(
            "DeepSeek API key chưa được cấu hình. Vui lòng cấu hình API Key trong mục Cài đặt hoặc file .env."
        )

    client = _llm_client(api_key)

    system_prompt = (
        "Bạn là Agent Bác sĩ Lâm sàng AI, hỗ trợ bác sĩ con người đưa ra chẩn đoán sơ bộ. "
        "Bạn có công cụ để tra cứu tiền sử bệnh nhân và tra cứu Dược Thư Quốc Gia — hãy dùng chúng TRƯỚC KHI kết luận, thay vì đoán ngay.\n\n"
        "QUY TRÌNH BẮT BUỘC:\n"
        "1. Tiền sử bệnh nhân ĐÃ được nạp sẵn ở đầu tin nhắn, trong thẻ <tien_su_benh_nhan>. Hãy đọc nó trước tiên. Gọi 'xem_tien_su_benh_nhan' chỉ khi cần xem lại.\n"
        "2. Nếu còn nghi vấn về tiêu chuẩn chẩn đoán, triệu chứng đặc hiệu, hoặc thuốc liên quan, hãy gọi 'tra_cuu_duoc_thu' với từ khóa phù hợp để đối chiếu tài liệu gốc. Có thể gọi nhiều lần với từ khóa khác nhau nếu cần, nhưng không quá 3 lần tra cứu tổng cộng.\n"
        "3. Chỉ kết luận (không gọi thêm tool) khi đã có đủ căn cứ.\n"
        "4. Khi kết luận, trả lời DUY NHẤT một JSON object theo schema, không kèm markdown:\n"
        "{\n"
        "  \"diagnosis_primary\": \"Chẩn đoán chính, kèm mã ICD-10 trong ngoặc đơn\",\n"
        "  \"diagnosis_differentials\": [\"Chẩn đoán phân biệt kèm ICD-10\", \"...\"],\n"
        "  \"reasoning\": \"Lập luận lâm sàng ngắn gọn, PHẢI nêu rõ đã dựa vào tiền sử và/hoặc tài liệu tra cứu nào để đi đến kết luận\"\n"
        "}\n"
        "Nếu tiền sử có dị ứng thuốc hoặc bệnh nền liên quan trực tiếp, PHẢI đề cập trong reasoning."
    )

    # Nạp sẵn tiền sử thay vì trông vào việc agent tự gọi tool. Đo trên
    # ToolFailBench (2026): tỉ lệ BỎ QUA tool trong các tác vụ BẮT BUỘC phải gọi
    # là 11,8%–20,6% tùy mô hình, và các tác giả kết luận kỷ luật gọi tool là
    # thuộc tính của mô hình chứ không phải của câu lệnh hệ thống. Nghĩa là dòng
    # "Luôn gọi 'xem_tien_su_benh_nhan'" ở trên trước đây là lời khuyên, và cứ
    # khoảng 1 trên 7 lần chẩn đoán được đưa ra mà chưa hề đọc mục dị ứng.
    # Tool vẫn giữ nguyên để agent xem lại khi cần; chỉ khác là nó không còn là
    # đường DUY NHẤT để tiền sử đi vào.
    patient_ctx, context_block = patient_context.build_prompt_block(patient_id)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context_block + f"Triệu chứng bệnh nhân hiện tại: {symptoms}\n\nHãy điều tra và đưa ra chẩn đoán."}
    ]

    trace: List[Dict[str, Any]] = []
    sources_used: List[Dict[str, Any]] = []
    seen_source_keys = set()

    for step in range(MAX_AGENT_STEPS):
        is_last_step = step == MAX_AGENT_STEPS - 1

        call_kwargs: Dict[str, Any] = dict(
            model=config.DEEPSEEK_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=1200,
        )
        if is_last_step:
            messages.append({
                "role": "user",
                "content": "Đã đủ thông tin. Hãy kết luận NGAY bằng JSON đúng schema, KHÔNG gọi thêm công cụ."
            })
            call_kwargs["response_format"] = {"type": "json_object"}
        else:
            call_kwargs["tools"] = TOOLS
            call_kwargs["tool_choice"] = "auto"

        response = client.chat.completions.create(**call_kwargs)
        msg = response.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []

        if not tool_calls:
            return _parse_final_answer(msg.content or "", trace, sources_used, patient_ctx)

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments or "{}")
            except (TypeError, ValueError):
                fn_args = {}

            if fn_name == "xem_tien_su_benh_nhan":
                result_text = _summarize_patient_history(patient_id)
                trace.append({
                    "tool": fn_name,
                    "label": "Xem tiền sử bệnh nhân",
                    "input": None,
                    "output_summary": result_text[:300],
                })
            elif fn_name == "tra_cuu_duoc_thu":
                query = str(fn_args.get("query") or "").strip() or symptoms
                try:
                    hits = search_literature_fn(query) or []
                except Exception:
                    hits = []
                brief_hits = []
                for h in hits[:4]:
                    brief_hits.append({
                        "doc_name": h.get("doc_name"),
                        "page_num": h.get("page_num"),
                        "text": (h.get("text") or "")[:600],
                    })
                    key = (h.get("doc_name"), str(h.get("page_num")))
                    if key not in seen_source_keys:
                        seen_source_keys.add(key)
                        sources_used.append({
                            "doc_name": h.get("doc_name"),
                            "page_num": h.get("page_num"),
                            "snippet": (h.get("text") or "")[:200],
                        })
                result_text = (
                    json.dumps(brief_hits, ensure_ascii=False)
                    if brief_hits else "Không tìm thấy tài liệu liên quan trong Dược Thư."
                )
                trace.append({
                    "tool": fn_name,
                    "label": f'Tra cứu Dược thư: "{query}"',
                    "input": query,
                    "output_summary": (
                        f"Tìm thấy {len(brief_hits)} đoạn tài liệu liên quan."
                        if brief_hits else "Không tìm thấy tài liệu liên quan."
                    ),
                })
            else:
                result_text = "Công cụ không xác định."
                trace.append({"tool": fn_name, "label": fn_name, "input": fn_args, "output_summary": result_text})

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_text,
            })

    # Should not normally be reached: the last loop iteration forces tools off.
    return {
        "diagnosis_primary": "",
        "diagnosis_differentials": [],
        "reasoning": "AI Agent không thể đưa ra kết luận sau nhiều bước tra cứu. Vui lòng thử lại.",
        "agent_trace": trace,
        "agent_sources": sources_used,
        "patient_context": patient_ctx,
    }
