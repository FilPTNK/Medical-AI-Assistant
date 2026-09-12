import json
import re
import uuid
import httpx
from openai import OpenAI
import config
from typing import List, Dict, Any, Optional

# Trần thời gian cho mọi lệnh gọi LLM.
#
# openai>=2 mặc định read timeout 600s và max_retries=2, nên một kết nối bị
# treo giữ request tới 30 phút mà frontend không nhận được gì — đúng triệu
# chứng "hỏi xong 15 phút không thấy trả lời". Đặt trần rõ ràng: kết nối 5s,
# đọc 120s (đủ cho câu dài nhất ~4000 token ở ~100 tok/s), thử lại tối đa 1
# lần → xấu nhất ~4 phút thay vì 30 phút.
LLM_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)
LLM_MAX_RETRIES = 1

# Riêng cho đường tra cứu y văn chảy dần.
#
# Khi stream, `read` không còn là "chờ cả câu trả lời" mà là "chờ mẩu chữ tiếp
# theo" — đo được chữ đầu tiên về sau 886ms, chậm nhất 1,63s. 15s là 9 lần con
# số chậm nhất đó, đủ rộng cho một lần mạng chậm và đủ chặt để không ai nhìn
# vòng xoay hai phút.
#
# max_retries=0 là CỐ Ý. Bác sĩ đã chốt: không tự thử lại. Với retry=1, một lần
# treo thành hai lần chờ liên tiếp mà không ai được báo, nên cái chờ dài gấp đôi
# và trần thời gian ở main.py mất tác dụng. Muốn thử lại thì bác sĩ bấm lại.
STREAM_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=30.0, pool=5.0)
STREAM_MAX_RETRIES = 0


def _llm_client(api_key: str, streaming: bool = False) -> OpenAI:
    """OpenAI client trỏ tới DeepSeek, luôn kèm timeout và giới hạn retry."""
    return OpenAI(
        api_key=api_key,
        base_url=config.DEEPSEEK_API_URL,
        timeout=STREAM_TIMEOUT if streaming else LLM_TIMEOUT,
        max_retries=STREAM_MAX_RETRIES if streaming else LLM_MAX_RETRIES,
    )

NO_KEY_MESSAGE = (
    "DeepSeek API key is not configured. "
    "Please click the 'Settings' gear in the top right to configure your API key, "
    "or add it to your `.env` file in the project folder."
)


def _build_answer_messages(query: str, context_chunks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Dựng messages cho câu trả lời tra cứu y văn.

    Tách riêng vì có HAI đường dùng chung đúng bộ prompt này: `generate_answer`
    (chờ sinh xong) và `stream_answer` (chảy dần). Để hai bản sao thì sớm muộn
    một bên được sửa quy tắc trích dẫn mà bên kia không, và bác sĩ nhận câu trả
    lời khác nhau tuỳ đường nào được gọi.
    """
    # Format the context text for the model
    context_str = ""
    for idx, chunk in enumerate(context_chunks):
        # Nhãn trích dẫn dạng người đọc nếu có ("Dược thư QGVN 2022, Q.1 — tr. 297"),
        # để mô hình nhắc đúng tên sách và số quyển thay vì ID kỹ thuật.
        label = chunk.get("citation") or f"{chunk['doc_name']}, Page: {chunk['page_num']}"
        context_str += f"[{idx+1}] Source: {label}\n"
        # Tên thuốc của đoạn này do OCR đọc hỏng. Nội dung vẫn dùng được, nhưng
        # phải nói rõ cho model, nếu không nó sẽ trích dẫn chuỗi rác như
        # "3AMBUTEROL" y hệt một tên thuốc có thật.
        if chunk.get("name_suspect"):
            context_str += (
                "Warning: tên thuốc của đoạn này bị lỗi OCR, KHÔNG đáng tin. "
                "Dùng nội dung nhưng tuyệt đối không nêu chuỗi đó như tên thuốc; "
                "nếu cần thì nói rõ tên trong tài liệu không đọc được.\n"
            )
        context_str += f"Content: {chunk['text']}\n\n"

    system_prompt = (
        "Bạn là Trợ lý Y tế Thông minh (Medical RAG Assistant) chuyên nghiệp và chính xác.\n"
        "Nhiệm vụ của bạn là hỗ trợ bác sĩ tra cứu thông tin trong các sách dược thư và tài liệu y khoa được cung cấp.\n"
        "Hãy phân tích kỹ các đoạn ngữ cảnh (Context) bên dưới và trả lời câu hỏi của người dùng bằng tiếng Việt.\n\n"
        "QUY TẮC BẮT BUỘC:\n"
        "1. Trả lời HOÀN TOÀN dựa trên các dữ kiện có trong ngữ cảnh được cung cấp. Tuyệt đối không tự suy diễn hoặc bịa đặt thông tin y khoa ngoài tài liệu.\n"
        "2. TRÍCH DẪN NGUỒN CHUẨN XÁC: Ngay sau mỗi luận điểm y khoa, chỉ định, liều dùng hoặc chống chỉ định cụ thể, BẮT BUỘC chèn ký hiệu trích dẫn dạng số trong ngoặc vuông như [1], [2], [3] tương ứng với số thứ tự nguồn trong Context (Ví dụ: 'Amikacin là kháng sinh bán tổng hợp thuộc nhóm Aminosid [1], được chỉ định trong nhiễm khuẩn huyết nặng [1] với liều 15mg/kg/ngày chia làm 2-3 lần [2]').\n"
        "3. Nếu thông tin không có trong tài liệu được cung cấp, hãy nêu rõ: 'Không tìm thấy thông tin này trong tài liệu y văn đã chỉ mục. Vui lòng kiểm tra lại tài liệu đã tải lên.'\n"
        "4. Trình bày khoa học, rõ ràng (sử dụng gạch đầu dòng cho Chỉ định, Liều dùng, Chống chỉ định, Tác dụng phụ, Lưu ý)."
    )

    user_prompt = f"Context:\n{context_str}\nQuestion: {query}\n\nAnswer:"

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def generate_answer(query: str, context_chunks: List[Dict[str, Any]], custom_api_key: str = "") -> str:
    """
    Calls the DeepSeek API (using OpenAI client) to generate an answer
    based on the provided document contexts.
    """
    # Use custom key if provided, otherwise config key
    api_key = custom_api_key if custom_api_key else config.DEEPSEEK_API_KEY

    if not api_key:
        return NO_KEY_MESSAGE

    try:
        # Initialize OpenAI client with DeepSeek credentials
        client = _llm_client(api_key)

        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=_build_answer_messages(query, context_chunks),
            temperature=0.1,  # Low temperature for factuality
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling DeepSeek API: {e}")
        return f"Error calling DeepSeek API: {str(e)}\n\n(Please check your connection and DEEPSEEK_API_KEY settings in .env)"


def stream_answer(query: str, context_chunks: List[Dict[str, Any]], custom_api_key: str = ""):
    """Câu trả lời tra cứu y văn, chảy dần theo từng đoạn.

    Sinh ra các cặp ``(kind, payload)``:

    - ``("delta", "…")`` — một mẩu chữ mới, nối vào cuối phần đã có
    - ``("error", "…")`` — câu báo lỗi đọc được, dừng tại đây

    KHÔNG bắt lỗi rồi trả nó ra như một câu trả lời. `generate_answer` làm thế:
    mọi ngoại lệ bị biến thành chuỗi "Error calling DeepSeek API: …" và đi vào
    đúng chỗ mà bác sĩ đọc câu trả lời y khoa, đồng thời được ghi vào lịch sử
    tra cứu như một câu trả lời thật. Ở đây lỗi là lỗi, và phía gọi quyết định
    hiện gì.
    """
    api_key = custom_api_key if custom_api_key else config.DEEPSEEK_API_KEY
    if not api_key:
        yield ("error", NO_KEY_MESSAGE)
        return

    try:
        client = _llm_client(api_key, streaming=True)
        stream = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=_build_answer_messages(query, context_chunks),
            temperature=0.1,
            max_tokens=1000,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            piece = chunk.choices[0].delta.content
            if piece:
                yield ("delta", piece)
    except Exception as e:
        print(f"Lỗi khi stream câu trả lời y văn: {type(e).__name__}: {e}")
        yield ("error", f"{type(e).__name__}: {e}")

def _strip_json_fences(content: str) -> str:
    """Strips ```json ... ``` code fences if the model wrapped its JSON output in one."""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*\n", "", content)
        content = re.sub(r"\n```\s*$", "", content)
    return content.strip()


_VN_QUESTION_TAIL_PATTERNS = [
    r"\s*như thế nào\s*\??$",
    r"\s*là (bao nhiêu|gì)\s*\??$",
    r"\s*(kéo dài )?bao lâu( rồi)?\s*\??$",
    r"\s*ra sao\s*\??$",
    r"\s*\?$",
]


def _strip_question_tail(label: str) -> str:
    """Best-effort fallback for turning a question into a bare phrase, used only when the LLM
    forgets to supply the dedicated *_note field the prompt asks for."""
    text = (label or "").strip()
    for pattern in _VN_QUESTION_TAIL_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    return text


def _derive_confirmed_note(label: str) -> str:
    text = (label or "").strip()
    m = re.match(r"^Có\s+(.+?)\s+không\s*\??$", text, flags=re.IGNORECASE)
    if m:
        phrase = m.group(1).strip()
        return phrase[:1].upper() + phrase[1:] if phrase else text
    stripped = _strip_question_tail(text)
    return stripped or text


def _derive_excluded_note(confirmed_note: str) -> str:
    if not confirmed_note:
        return ""
    return f"Không {confirmed_note[0].lower()}{confirmed_note[1:]}"


def _normalize_tree_option(option: Dict[str, Any], seen_ids: set) -> Optional[Dict[str, Any]]:
    """Normalizes a single 'choice' option: unique id, label, hypothetical_focus, note, children."""
    if not isinstance(option, dict):
        return None

    raw_id = str(option.get("id") or "").strip() or uuid.uuid4().hex[:10]
    opt_id = raw_id
    while opt_id in seen_ids:
        opt_id = f"{raw_id}_{uuid.uuid4().hex[:6]}"
    seen_ids.add(opt_id)

    label = str(option.get("label") or "").strip() or "Lựa chọn"

    focus = option.get("hypothetical_focus")
    focus = str(focus).strip() if focus else None

    # Natural-language phrasing to record in the patient's symptom notes when this option is
    # picked (e.g. "Dịch mũi đục, xanh hoặc vàng") — falls back to the button label itself if
    # the LLM didn't provide one, since a short option label often already reads fine alone.
    note = option.get("note")
    note = str(note).strip() if note else label

    return {
        "id": opt_id,
        "label": label,
        "hypothetical_focus": focus,
        "note": note,
        "children": _normalize_tree_nodes(option.get("children"), seen_ids)
    }


def _normalize_tree_nodes(nodes: Optional[List[Dict[str, Any]]], seen_ids: set) -> List[Dict[str, Any]]:
    """Recursively normalizes diagnosis-tree nodes: ensures unique id, label, layer,
    answer_type ('boolean' | 'choice' | 'text') and the fields that go with it."""
    normalized = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue

        raw_id = str(node.get("id") or "").strip() or uuid.uuid4().hex[:10]
        node_id = raw_id
        while node_id in seen_ids:
            node_id = f"{raw_id}_{uuid.uuid4().hex[:6]}"
        seen_ids.add(node_id)

        label = str(node.get("label") or "").strip() or "Triệu chứng"

        try:
            layer = int(node.get("layer", 1))
        except (TypeError, ValueError):
            layer = 1

        focus = node.get("hypothetical_focus")
        focus = str(focus).strip() if focus else None

        answer_type = str(node.get("answer_type") or "boolean").strip().lower()
        if answer_type not in ("boolean", "choice", "text"):
            answer_type = "boolean"

        entry = {
            "id": node_id,
            "label": label,
            "layer": layer,
            "hypothetical_focus": focus,
            "answer_type": answer_type,
            "children": [],
            "options": [],
            "input_hint": None,
            "confirmed_note": None,
            "excluded_note": None,
            "note_template": None
        }

        if answer_type == "choice":
            options = [_normalize_tree_option(o, seen_ids) for o in (node.get("options") or [])]
            entry["options"] = [o for o in options if o]
            if not entry["options"]:
                # A choice node with no valid options is meaningless — fall back to boolean
                # so the doctor still gets a usable Có/Không question instead of a dead end.
                entry["answer_type"] = "boolean"
                answer_type = "boolean"
                entry["children"] = _normalize_tree_nodes(node.get("children"), seen_ids)
        elif answer_type == "text":
            hint = node.get("input_hint")
            entry["input_hint"] = str(hint).strip() if hint else None
            template = node.get("note_template")
            template = str(template).strip() if template else ""
            if "{value}" not in template:
                # Fallback: turn the question into a bare phrase and tack the value on, e.g.
                # "Sổ mũi kéo dài bao lâu rồi?" -> "Sổ mũi kéo dài {value}".
                template = f"{_strip_question_tail(label)} {{value}}".strip()
            entry["note_template"] = template
        else:
            entry["children"] = _normalize_tree_nodes(node.get("children"), seen_ids)

        if answer_type == "boolean":
            confirmed_note = node.get("confirmed_note")
            confirmed_note = str(confirmed_note).strip() if confirmed_note else ""
            if not confirmed_note:
                confirmed_note = _derive_confirmed_note(label)
            entry["confirmed_note"] = confirmed_note

            excluded_note = node.get("excluded_note")
            excluded_note = str(excluded_note).strip() if excluded_note else ""
            if not excluded_note:
                excluded_note = _derive_excluded_note(confirmed_note)
            entry["excluded_note"] = excluded_note

        normalized.append(entry)
    return normalized


def _format_context_block(context_chunks: Optional[List[Dict[str, Any]]]) -> str:
    if not context_chunks:
        return ""
    context_str = ""
    for idx, chunk in enumerate(context_chunks):
        context_str += f"[{idx + 1}] {chunk.get('doc_name', '')} (trang {chunk.get('page_num', '?')}): {chunk.get('text', '')}\n\n"
    return context_str


def generate_diagnosis_tree(description: str, custom_api_key: str = "", context_chunks: Optional[List[Dict[str, Any]]] = None) -> dict:
    """
    Call 1: Asks DeepSeek to act as an ENT (Tai Mui Hong) expert agent and generate a full
    recursive diagnostic decision tree (JSON) from the patient's free-text description.
    """
    api_key = custom_api_key if custom_api_key else config.DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError(
            "DeepSeek API key chưa được cấu hình. Vui lòng cấu hình API Key trong mục Cài đặt hoặc file .env."
        )

    system_prompt = (
        "Bạn là một Agent Chuyên gia Tai Mũi Họng (ENT) chịu trách nhiệm dựng Cây Suy Luận Chẩn Đoán (Diagnostic Decision Tree).\n"
        "Nhiệm vụ: Phân tích mô tả của bệnh nhân và tạo một Cây Quyết Định phân nhánh đệ quy dưới dạng JSON.\n\n"
        "Quy tắc bắt buộc:\n"
        "1. Phạm vi triệu chứng: Chỉ tạo các node thuộc phạm vi BÁC SĨ HỎI BỆNH (hỏi tiền sử, triệu chứng cơ năng như sốt, đau, nghẹt mũi, ù tai...). "
        "TỰ ĐỘNG LOẠI BỎ các yếu tố cần soi nội soi, chụp CT, hay xét nghiệm.\n"
        "2. Tính độc lập của nhánh: Mỗi node con (child node) PHẢI là nhánh hỏi sâu chuyên biệt dành riêng cho node cha đó. Không dùng chung các danh mục câu hỏi chung chung.\n"
        "3. Độ sâu: Tạo cây từ 2 đến 4 tầng (layers). Tầng càng sâu càng đi vào các triệu chứng đặc hiệu của giả thuyết chẩn đoán đó.\n"
        "4. Mỗi node PHẢI có một \"id\" dạng chuỗi duy nhất trong toàn bộ cây (ví dụ node_1, node_1_1, node_1_1_2).\n"
        "5. Mỗi node PHẢI có trường \"answer_type\" chọn đúng MỘT trong 3 loại, tùy theo bản chất câu hỏi:\n"
        "   - \"boolean\": câu hỏi có/không thật sự độc lập (vd \"Có sốt không?\", \"Có đau ngực không?\"). Dùng \"children\" cho các câu hỏi sâu hơn, chỉ hỏi tiếp khi câu trả lời là Có. "
        "PHẢI kèm \"confirmed_note\": cụm từ khẳng định ngắn gọn, TỰ NHIÊN như con người ghi bệnh án, dùng khi câu trả lời là Có, KHÔNG lặp lại dạng câu hỏi (vd label \"Có đau họng không?\" → confirmed_note \"Đau họng\", KHÔNG phải \"Có đau họng không?: Có\"). "
        "PHẢI kèm \"excluded_note\": cụm từ phủ định tương ứng dùng khi câu trả lời là Không (vd \"Không đau họng\").\n"
        "   - \"choice\": câu hỏi có 2 hoặc nhiều lựa chọn LOẠI TRỪ LẪN NHAU (vd \"Đau bụng từ từ hay quặn thắt?\", \"Sốt liên tục hay sốt cơn?\"). Dùng \"options\": mảng các lựa chọn, mỗi lựa chọn có \"id\", \"label\" (nhãn ngắn hiển thị trên nút bấm), \"hypothetical_focus\", \"children\" riêng, và bắt buộc có \"note\": cụm từ TỰ NHIÊN đầy đủ chủ ngữ để ghi vào bệnh án khi chọn lựa chọn đó "
        "(vd node label \"Tính chất dịch mũi như thế nào?\" với option label \"Dịch đục, xanh hoặc vàng\" → note \"Dịch mũi đục, xanh hoặc vàng\"; option label đã tự nhiên sẵn như \"Sốt từng cơn\" thì note giữ nguyên \"Sốt từng cơn\", KHÔNG được ghép label câu hỏi phía trước).\n"
        "   - \"text\": câu hỏi cần bác sĩ NHẬP một giá trị định lượng/mở, không phải chọn (vd \"Sốt về chiều kéo dài bao lâu?\", \"Đau bao nhiêu ngày rồi?\", \"Nhiệt độ sốt cao nhất?\"). Dùng \"input_hint\" gợi ý định dạng nhập (vd \"Ví dụ: 10 ngày\"). "
        "PHẢI kèm \"note_template\": mẫu câu TỰ NHIÊN chứa đúng placeholder \"{value}\" ở vị trí giá trị bác sĩ nhập vào sẽ được chèn vào, để ghép thành một câu hoàn chỉnh khi ghi bệnh án "
        "(vd label \"Sổ mũi kéo dài bao lâu rồi?\" → note_template \"Sổ mũi kéo dài {value}\"; label \"Nhiệt độ sốt cao nhất?\" → note_template \"Sốt cao nhất {value}\"). Node \"text\" luôn là node lá, KHÔNG có children.\n"
        "6. CẤM TUYỆT ĐỐI tạo hai node anh em (sibling) mà một node là PHỦ ĐỊNH LOGIC của node kia rồi hỏi Có/Không riêng từng node "
        "(vd sai: node \"Dưới 1 tuần\" [Có/Không] và node \"Trên 1 tuần\" [Có/Không] cạnh nhau — hai câu trả lời này luôn ngược nhau nên vô nghĩa; "
        "vd sai khác: \"Có khàn tiếng\" [Có/Không] và \"Không khàn tiếng\" [Có/Không]). "
        "Trong mọi trường hợp như vậy, PHẢI gộp lại thành DUY NHẤT một node \"choice\" với các \"options\" loại trừ nhau (vd một node \"Thời gian sốt về chiều\" với options [\"Dưới 1 tuần\", \"Trên 1 tuần\"], hoặc dùng \"text\" nếu cần giá trị chính xác hơn thay vì chia mốc tùy tiện).\n"
        "7. Các trường confirmed_note/excluded_note/note/note_template dùng để GHI THẲNG vào bệnh án điện tử — PHẢI đọc tự nhiên như bác sĩ tự tay ghi chú lâm sàng, không lặp lại nguyên văn câu hỏi, không có dấu hai chấm hay dấu hỏi chấm.\n\n"
        "Định dạng: Xuất đúng JSON object theo schema sau, không kèm markdown hay giải thích thêm:\n"
        "{\n"
        "  \"patient_summary\": \"Tóm tắt ngắn gọn tình trạng bệnh nhân\",\n"
        "  \"root_nodes\": [\n"
        "    {\n"
        "      \"id\": \"node_1\",\n"
        "      \"label\": \"Có đau họng không?\",\n"
        "      \"layer\": 1,\n"
        "      \"hypothetical_focus\": \"Nghi ngờ bệnh lý X (tùy chọn, có thể null)\",\n"
        "      \"answer_type\": \"boolean\",\n"
        "      \"confirmed_note\": \"Đau họng\",\n"
        "      \"excluded_note\": \"Không đau họng\",\n"
        "      \"children\": [\n"
        "        {\n"
        "          \"id\": \"node_1_1\",\n"
        "          \"label\": \"Tính chất dịch mũi như thế nào?\",\n"
        "          \"layer\": 2,\n"
        "          \"hypothetical_focus\": null,\n"
        "          \"answer_type\": \"choice\",\n"
        "          \"options\": [\n"
        "            { \"id\": \"opt_1\", \"label\": \"Dịch trong, loãng\", \"note\": \"Dịch mũi trong, loãng\", \"hypothetical_focus\": \"Nghi ngờ bệnh lý Y\", \"children\": [] },\n"
        "            { \"id\": \"opt_2\", \"label\": \"Dịch đục, xanh hoặc vàng\", \"note\": \"Dịch mũi đục, xanh hoặc vàng\", \"hypothetical_focus\": \"Nghi ngờ bệnh lý Z\", \"children\": [] }\n"
        "          ]\n"
        "        },\n"
        "        {\n"
        "          \"id\": \"node_1_2\",\n"
        "          \"label\": \"Sổ mũi kéo dài bao lâu rồi?\",\n"
        "          \"layer\": 2,\n"
        "          \"hypothetical_focus\": null,\n"
        "          \"answer_type\": \"text\",\n"
        "          \"input_hint\": \"Ví dụ: 10 ngày\",\n"
        "          \"note_template\": \"Sổ mũi kéo dài {value}\"\n"
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}"
    )

    context_block = _format_context_block(context_chunks)
    user_prompt = f"Mô tả bệnh nhân: {description}\n\n"
    if context_block:
        user_prompt += f"Tài liệu y khoa tham khảo:\n{context_block}\n"
    user_prompt += "Hãy tạo Cây Chẩn Đoán JSON theo đúng schema đã mô tả."

    client = _llm_client(api_key)
    response = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        max_tokens=4000,
        response_format={"type": "json_object"}
    )
    content = _strip_json_fences(response.choices[0].message.content)
    parsed = json.loads(content)

    seen_ids: set = set()
    root_nodes = _normalize_tree_nodes(parsed.get("root_nodes"), seen_ids)

    return {
        "patient_summary": str(parsed.get("patient_summary") or description[:160]),
        "root_nodes": root_nodes
    }


def suggest_endoscopy_exam(
    confirmed_symptoms: List[str],
    excluded_symptoms: List[str],
    custom_api_key: str = "",
    context_chunks: Optional[List[Dict[str, Any]]] = None
) -> dict:
    """
    Call 2: Given the confirmed/excluded symptoms from the tree, asks DeepSeek to suggest
    which regions need endoscopy and which physical exam maneuvers/signs to focus on.
    """
    api_key = custom_api_key if custom_api_key else config.DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError(
            "DeepSeek API key chưa được cấu hình. Vui lòng cấu hình API Key trong mục Cài đặt hoặc file .env."
        )

    system_prompt = (
        "Bạn là Chuyên gia Tai Mũi Họng. Dựa trên tập triệu chứng cơ năng mà bệnh nhân xác nhận CÓ (confirmed_symptoms) "
        "và LOẠI TRỪ (excluded_symptoms), hãy đưa ra định hướng chi tiết cho bác sĩ về các vị trí cần tập trung nội soi và khám lâm sàng.\n\n"
        "Yêu cầu đầu ra là một JSON object với các trường:\n"
        "- endoscopy_focus: Danh sách các vị trí nội soi ưu tiên (Tai, Mũi - Xoang, Vòm họng, Hạ họng - Thanh quản...), mỗi phần tử có 'region' và 'instructions' (mô tả chi tiết cần quan sát kỹ những gì).\n"
        "- physical_exam_focus: Mảng chuỗi các thao tác khám thể chất cần làm (sờ nắn hạch cổ, khám dây thần kinh sọ, đè lưỡi...).\n"
        "- key_signs_to_look_for: Mảng chuỗi các dấu hiệu thực thể quan trọng cần truy tìm để xác nhận/loại trừ bệnh.\n\n"
        "Xuất đúng JSON object theo schema:\n"
        "{\n"
        "  \"recommended_procedures\": {\n"
        "    \"endoscopy_focus\": [ { \"region\": \"...\", \"instructions\": \"...\" } ],\n"
        "    \"physical_exam_focus\": [ \"...\" ],\n"
        "    \"key_signs_to_look_for\": [ \"...\" ]\n"
        "  }\n"
        "}\n"
        "Không kèm markdown hay giải thích thêm ngoài JSON."
    )

    context_block = _format_context_block(context_chunks)
    confirmed_str = ", ".join(confirmed_symptoms) if confirmed_symptoms else "Không có"
    excluded_str = ", ".join(excluded_symptoms) if excluded_symptoms else "Không có"
    user_prompt = f"Triệu chứng CÓ (confirmed_symptoms): {confirmed_str}\nTriệu chứng LOẠI TRỪ (excluded_symptoms): {excluded_str}\n\n"
    if context_block:
        user_prompt += f"Tài liệu y khoa tham khảo:\n{context_block}\n"
    user_prompt += "Hãy đưa ra định hướng khám & nội soi dạng JSON theo đúng schema."

    client = _llm_client(api_key)
    response = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_tokens=1200,
        response_format={"type": "json_object"}
    )
    content = _strip_json_fences(response.choices[0].message.content)
    parsed = json.loads(content)

    procedures = parsed.get("recommended_procedures", parsed)
    return {
        "endoscopy_focus": procedures.get("endoscopy_focus", []) or [],
        "physical_exam_focus": procedures.get("physical_exam_focus", []) or [],
        "key_signs_to_look_for": procedures.get("key_signs_to_look_for", []) or []
    }


def generate_final_diagnosis(
    confirmed_symptoms: List[str],
    excluded_symptoms: List[str],
    exam_notes: str,
    custom_api_key: str = "",
    context_chunks: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Call 3: Combines confirmed/excluded functional symptoms with the doctor's real endoscopy/physical
    exam notes to produce the final top-10 ranked differential diagnosis list.
    """
    api_key = custom_api_key if custom_api_key else config.DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError(
            "DeepSeek API key chưa được cấu hình. Vui lòng cấu hình API Key trong mục Cài đặt hoặc file .env."
        )

    system_prompt = (
        "Bạn là Chuyên gia Tai Mũi Họng hàng đầu. Hãy kết hợp thông tin triệu chứng cơ năng (confirmed_symptoms, excluded_symptoms) "
        "và kết quả khám lâm sàng/nội soi thực tế (endoscopy_and_physical_exam_notes) để đưa ra Top 10 chẩn đoán phân biệt phù hợp nhất.\n\n"
        "Yêu cầu:\n"
        "- Trả về đúng 10 bệnh lý sắp xếp theo độ ưu tiên từ cao xuống thấp.\n"
        "- Với mỗi bệnh lý, chỉ rõ: disease_name (Tên bệnh, cả Tiếng Việt và Tiếng Anh), icd10 (Mã ICD-10 tương ứng), "
        "confidence (số nguyên 0-100, tỷ lệ phần trăm phù hợp), reasoning (lập luận lâm sàng, đối chiếu giữa triệu chứng cơ năng và hình ảnh nội soi), "
        "red_flags (cảnh báo nếu bệnh lý nằm trong nhóm nguy cơ cao hoặc cấp cứu, để chuỗi rỗng nếu không có).\n\n"
        "Xuất đúng JSON object theo schema (bắt buộc phải là JSON object có khóa 'diagnoses', KHÔNG được trả về mảng trần):\n"
        "{\n"
        "  \"diagnoses\": [\n"
        "    { \"disease_name\": \"...\", \"icd10\": \"...\", \"confidence\": 85, \"reasoning\": \"...\", \"red_flags\": \"...\" }\n"
        "  ]\n"
        "}\n"
        "Không kèm markdown hay giải thích thêm ngoài JSON."
    )

    context_block = _format_context_block(context_chunks)
    confirmed_str = ", ".join(confirmed_symptoms) if confirmed_symptoms else "Không có"
    excluded_str = ", ".join(excluded_symptoms) if excluded_symptoms else "Không có"
    user_prompt = (
        f"confirmed_symptoms: {confirmed_str}\n"
        f"excluded_symptoms: {excluded_str}\n"
        f"endoscopy_and_physical_exam_notes: {exam_notes}\n\n"
    )
    if context_block:
        user_prompt += f"Tài liệu y khoa tham khảo:\n{context_block}\n\n"
    user_prompt += "Hãy trả về Top 10 chẩn đoán dạng JSON theo đúng schema."

    client = _llm_client(api_key)
    response = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_tokens=2500,
        response_format={"type": "json_object"}
    )
    content = _strip_json_fences(response.choices[0].message.content)
    parsed = json.loads(content)

    raw_list = parsed.get("diagnoses") if isinstance(parsed, dict) else parsed
    if not isinstance(raw_list, list):
        raw_list = []

    validated = []
    for item in raw_list[:10]:
        if not isinstance(item, dict):
            continue
        try:
            confidence = int(item.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0
        validated.append({
            "disease_name": str(item.get("disease_name", "Bệnh chưa rõ")),
            "icd10": str(item.get("icd10", "")),
            "confidence": max(0, min(100, confidence)),
            "reasoning": str(item.get("reasoning", "")),
            "red_flags": str(item.get("red_flags", "") or "")
        })
    return validated


def generate_treatment_suggestion(
    selected_diagnoses: List[Dict[str, Any]],
    exam_notes: str,
    custom_api_key: str = "",
    context_chunks: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Given the diagnoses the doctor picked (out of the Top 10 from Call 3), asks DeepSeek to
    suggest an initial medication list, non-drug recommendations, and care instructions —
    the same shape the Patients tab's visit/treatment form already stores.
    """
    api_key = custom_api_key if custom_api_key else config.DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError(
            "DeepSeek API key chưa được cấu hình. Vui lòng cấu hình API Key trong mục Cài đặt hoặc file .env."
        )

    system_prompt = (
        "Bạn là Chuyên gia Tai Mũi Họng kiêm Dược lâm sàng. Dựa trên (các) chẩn đoán mà bác sĩ đã CHỌN "
        "(selected_diagnoses) và ghi chú khám lâm sàng/nội soi (exam_notes), hãy đề xuất phác đồ điều trị ban đầu.\n\n"
        "Yêu cầu:\n"
        "- medications: danh sách thuốc gợi ý, mỗi thuốc có name (tên thuốc + hàm lượng), dosage (liều dùng mỗi lần), "
        "form (dạng bào chế), frequency (số lần/ngày hoặc thời gian dùng), instructions (lưu ý khi dùng, mỗi lưu ý một dòng).\n"
        "- no_drug_recommendations: khuyến nghị không dùng thuốc, mỗi khuyến nghị một dòng (chuỗi rỗng nếu không có).\n"
        "- care_instructions: hướng dẫn chăm sóc tại nhà, mỗi hướng dẫn một dòng (chuỗi rỗng nếu không có).\n"
        "- goals: mảng các mục tiêu điều trị ngắn gọn (ví dụ: \"Giảm nhanh triệu chứng\", \"Ngăn ngừa biến chứng\").\n"
        "- protocol_duration: thời gian điều trị dự kiến (ví dụ: \"5 - 7 ngày\").\n"
        "- treatment_method: phương pháp điều trị (ví dụ: \"Nội khoa\").\n"
        "- diet_regimen: chế độ ăn uống/sinh hoạt khuyến nghị (một câu ngắn).\n"
        "- precautions: lưu ý cần tránh trong quá trình điều trị (một câu ngắn).\n\n"
        "Xuất đúng JSON object theo schema:\n"
        "{\n"
        "  \"medications\": [ { \"name\": \"...\", \"dosage\": \"...\", \"form\": \"...\", \"frequency\": \"...\", \"instructions\": \"...\" } ],\n"
        "  \"no_drug_recommendations\": \"...\",\n"
        "  \"care_instructions\": \"...\",\n"
        "  \"goals\": [\"...\", \"...\"],\n"
        "  \"protocol_duration\": \"...\",\n"
        "  \"treatment_method\": \"...\",\n"
        "  \"diet_regimen\": \"...\",\n"
        "  \"precautions\": \"...\"\n"
        "}\n"
        "Không kèm markdown hay giải thích thêm ngoài JSON."
    )

    context_block = _format_context_block(context_chunks)
    diagnoses_str = "\n".join(
        f"- {d.get('disease_name', '')}" + (f" ({d.get('icd10')})" if d.get('icd10') else "")
        + (f": {d.get('reasoning')}" if d.get('reasoning') else "")
        for d in selected_diagnoses
    ) or "Không có"
    user_prompt = f"selected_diagnoses:\n{diagnoses_str}\n\nexam_notes: {exam_notes or 'Không có'}\n\n"
    if context_block:
        user_prompt += f"Tài liệu y khoa tham khảo:\n{context_block}\n\n"
    user_prompt += "Hãy đề xuất phác đồ điều trị ban đầu dạng JSON theo đúng schema."

    client = _llm_client(api_key)
    response = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_tokens=1800,
        response_format={"type": "json_object"}
    )
    content = _strip_json_fences(response.choices[0].message.content)
    parsed = json.loads(content)

    raw_meds = parsed.get("medications")
    medications = []
    if isinstance(raw_meds, list):
        for item in raw_meds:
            if not isinstance(item, dict):
                continue
            medications.append({
                "name": str(item.get("name", "")).strip(),
                "dosage": str(item.get("dosage", "")).strip(),
                "form": str(item.get("form", "")).strip(),
                "frequency": str(item.get("frequency", "")).strip(),
                "instructions": str(item.get("instructions", "") or "").strip()
            })
    medications = [m for m in medications if m["name"]]

    raw_goals = parsed.get("goals")
    goals = [str(g).strip() for g in raw_goals if str(g).strip()] if isinstance(raw_goals, list) else []

    return {
        "medications": medications,
        "no_drug_recommendations": str(parsed.get("no_drug_recommendations", "") or "").strip(),
        "care_instructions": str(parsed.get("care_instructions", "") or "").strip(),
        "goals": goals,
        "protocol_duration": str(parsed.get("protocol_duration", "") or "").strip(),
        "treatment_method": str(parsed.get("treatment_method", "") or "").strip(),
        "diet_regimen": str(parsed.get("diet_regimen", "") or "").strip(),
        "precautions": str(parsed.get("precautions", "") or "").strip(),
    }


def generate_document_comparison(
    query: str,
    per_document_contexts: List[Dict[str, Any]],
    custom_api_key: str = ""
) -> Dict[str, Any]:
    """Đối chiếu cùng một câu hỏi lâm sàng trên nhiều tài liệu/guideline khác nhau.

    `per_document_contexts` là danh sách {doc_name, chunks[]} — mỗi phần tử chứa
    các đoạn liên quan nhất *trong riêng tài liệu đó*, để mô hình so sánh được
    quan điểm của từng nguồn thay vì trộn chung thành một câu trả lời.
    """
    api_key = custom_api_key if custom_api_key else config.DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError(
            "DeepSeek API key chưa được cấu hình. Vui lòng cấu hình API Key trong mục Cài đặt hoặc file .env."
        )

    context_str = ""
    for doc in per_document_contexts:
        doc_name = doc.get("doc_name", "")
        context_str += f"### TÀI LIỆU: {doc_name}\n"
        chunks = doc.get("chunks") or []
        if not chunks:
            context_str += "(Không tìm thấy đoạn nào liên quan trong tài liệu này)\n\n"
            continue
        for chunk in chunks:
            context_str += f"- (Trang {chunk.get('page_num', '?')}) {chunk.get('text', '')}\n"
        context_str += "\n"

    system_prompt = (
        "Bạn là Chuyên gia Y khoa Dựa trên Bằng chứng (Evidence-Based Medicine), chuyên đối chiếu "
        "các hướng dẫn điều trị và tài liệu y văn khác nhau.\n"
        "Người dùng đưa ra MỘT câu hỏi lâm sàng và nội dung trích từ NHIỀU tài liệu khác nhau. "
        "Nhiệm vụ của bạn là so sánh xem các tài liệu này nói gì về câu hỏi đó.\n\n"
        "QUY TẮC:\n"
        "1. Chỉ dựa trên nội dung được cung cấp cho từng tài liệu. Tuyệt đối không suy diễn thêm.\n"
        "2. Nếu một tài liệu không đề cập tới vấn đề được hỏi, ghi rõ coverage = \"Không đề cập\" "
        "và để key_points rỗng — KHÔNG được lấy nội dung của tài liệu khác gán cho nó.\n"
        "3. agreements: các điểm mà từ 2 tài liệu trở lên cùng thống nhất.\n"
        "4. differences: các điểm khác biệt thực sự (khác liều, khác thứ tự ưu tiên, khác chỉ định, "
        "khác thời gian điều trị...). Với mỗi khác biệt, nêu rõ lập trường của từng tài liệu. "
        "Nếu các tài liệu không thực sự mâu thuẫn thì để mảng rỗng, không bịa ra khác biệt.\n"
        "5. conclusion: kết luận thực dụng cho bác sĩ lâm sàng, nêu rõ nên theo hướng nào và vì sao.\n\n"
        "YÊU CẦU ĐẦU RA LÀ JSON OBJECT ĐÚNG SCHEMA:\n"
        "{\n"
        "  \"summary\": \"Tóm tắt 1-2 câu về mức độ đồng thuận giữa các nguồn\",\n"
        "  \"per_document\": [\n"
        "    { \"doc_name\": \"tên tài liệu đúng như đã cho\", \"coverage\": \"Đầy đủ|Một phần|Không đề cập\",\n"
        "      \"stance\": \"Tóm tắt quan điểm của tài liệu này (1-3 câu)\",\n"
        "      \"key_points\": [\"ý chính 1\", \"ý chính 2\"],\n"
        "      \"pages\": [\"12\", \"48\"] }\n"
        "  ],\n"
        "  \"agreements\": [\"điểm đồng thuận 1\", \"điểm đồng thuận 2\"],\n"
        "  \"differences\": [\n"
        "    { \"topic\": \"Vấn đề khác biệt (ví dụ: Liều khởi đầu)\",\n"
        "      \"positions\": [ { \"doc_name\": \"...\", \"position\": \"...\" } ],\n"
        "      \"impact\": \"Ý nghĩa lâm sàng của khác biệt này\" }\n"
        "  ],\n"
        "  \"conclusion\": \"Khuyến nghị thực hành cho bác sĩ\"\n"
        "}\n"
        "Không xuất thêm bất kỳ văn bản nào ngoài JSON."
    )

    user_prompt = (
        f"Câu hỏi lâm sàng cần đối chiếu: {query}\n\n"
        f"Nội dung trích xuất theo từng tài liệu:\n{context_str}\n"
        "Hãy đối chiếu các tài liệu trên và xuất JSON theo đúng schema."
    )

    client = _llm_client(api_key)
    response = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.15,
        max_tokens=3000,
        response_format={"type": "json_object"}
    )
    parsed = json.loads(_strip_json_fences(response.choices[0].message.content))

    known_docs = {d.get("doc_name") for d in per_document_contexts}

    per_document = []
    for item in parsed.get("per_document") or []:
        if not isinstance(item, dict):
            continue
        doc_name = str(item.get("doc_name") or "").strip()
        if doc_name not in known_docs:
            # Bỏ qua tài liệu mà mô hình tự bịa ra ngoài danh sách bác sĩ đã chọn.
            continue
        raw_points = item.get("key_points")
        key_points = [str(p).strip() for p in raw_points if str(p).strip()] if isinstance(raw_points, list) else []
        raw_pages = item.get("pages")
        pages = [str(p).strip() for p in raw_pages if str(p).strip()] if isinstance(raw_pages, list) else []
        per_document.append({
            "doc_name": doc_name,
            "coverage": str(item.get("coverage") or "Một phần").strip(),
            "stance": str(item.get("stance") or "").strip(),
            "key_points": key_points,
            "pages": pages,
        })

    # Giữ nguyên thứ tự bác sĩ đã chọn, và bổ sung tài liệu mà mô hình bỏ sót.
    covered = {d["doc_name"] for d in per_document}
    for doc in per_document_contexts:
        name = doc.get("doc_name")
        if name not in covered:
            per_document.append({
                "doc_name": name,
                "coverage": "Không đề cập",
                "stance": "Không tìm thấy nội dung liên quan tới câu hỏi trong tài liệu này.",
                "key_points": [],
                "pages": [],
            })
    order = {doc.get("doc_name"): idx for idx, doc in enumerate(per_document_contexts)}
    per_document.sort(key=lambda d: order.get(d["doc_name"], 999))

    differences = []
    for item in parsed.get("differences") or []:
        if not isinstance(item, dict):
            continue
        positions = []
        for pos in item.get("positions") or []:
            if isinstance(pos, dict) and str(pos.get("doc_name") or "").strip() in known_docs:
                positions.append({
                    "doc_name": str(pos.get("doc_name")).strip(),
                    "position": str(pos.get("position") or "").strip(),
                })
        if positions:
            differences.append({
                "topic": str(item.get("topic") or "").strip(),
                "positions": positions,
                "impact": str(item.get("impact") or "").strip(),
            })

    raw_agreements = parsed.get("agreements")
    agreements = [str(a).strip() for a in raw_agreements if str(a).strip()] if isinstance(raw_agreements, list) else []

    return {
        "summary": str(parsed.get("summary") or "").strip(),
        "per_document": per_document,
        "agreements": agreements,
        "differences": differences,
        "conclusion": str(parsed.get("conclusion") or "").strip(),
    }


def generate_drug_report(
    query: str,
    context_chunks: List[Dict[str, Any]],
    custom_api_key: str = ""
) -> Dict[str, Any]:
    """
    Calls DeepSeek to generate a comprehensive, structured clinical drug report
    with NotebookLM-style citations [1], [2], table of contents, and quick takeaways.
    """
    api_key = custom_api_key if custom_api_key else config.DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError(
            "DeepSeek API key chưa được cấu hình. Vui lòng cấu hình API Key trong mục Cài đặt hoặc file .env."
        )

    # Format context chunks with numbered index for NotebookLM citations
    context_str = ""
    sources_meta = []
    for idx, chunk in enumerate(context_chunks):
        cite_id = idx + 1
        doc_name = chunk.get("doc_name", "THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf")
        page_num = chunk.get("page_num", 1)
        text_snippet = chunk.get("text", "")
        context_str += f"[{cite_id}] Tài liệu: {doc_name} ({page_num if str(page_num).startswith('Trang') else f'Trang {page_num}'})\nNội dung: {text_snippet}\n\n"
        sources_meta.append({
            "id": str(cite_id),
            "doc_name": doc_name,
            "page_num": str(page_num) if str(page_num).startswith("Trang") else f"Trang {page_num}",
            "file_size": chunk.get("file_size", "PDF • 61.8 MB"),
            "snippet": text_snippet[:300] + ("..." if len(text_snippet) > 300 else "")
        })

    system_prompt = (
        "Bạn là Chuyên gia Dược học Lâm sàng (Clinical Pharmacologist) và Cố vấn Y khoa cao cấp.\n"
        "Nhiệm vụ của bạn là tổng hợp và lập một Bản Báo Cáo Y Khoa Toàn Diện về thuốc hoặc nhóm thuốc được yêu cầu.\n\n"
        "QUY TẮC CẤU TRÚC BÁO CÁO (BẮT BUỘC ĐÚNG 9 MỤC THEO THỨ TỰ):\n"
        "1. Tổng quan: Định nghĩa hoạt chất, nhóm dược lý, cơ chế tác dụng cơ bản.\n"
        "2. Chỉ định: Các bệnh lý, hội chứng được phép điều trị (gạch đầu dòng rõ ràng).\n"
        "3. Liều dùng: Phân chia cụ thể Người lớn và Trẻ em, liều thông thường, khoảng cách liều, liều tối đa.\n"
        "4. Chống chỉ định: Các trường hợp tuyệt đối hoặc tương đối không được dùng thuốc.\n"
        "5. Tác dụng phụ: Phân loại thường gặp, ít gặp hoặc tác dụng không mong muốn nghiêm trọng.\n"
        "6. Tương tác thuốc: Các cặp tương tác quan trọng (với thuốc khác, thức ăn, cồn/rượu).\n"
        "7. Thận trọng: Các cảnh báo đặc biệt, đối tượng nguy cơ (bao gồm người suy gan/thận, người cao tuổi, phụ nữ có thai và cho con bú).\n"
        "8. Dạng bào chế: Các dạng thuốc và hàm lượng thông dụng trên lâm sàng.\n"
        "9. Bảo quản: Điều kiện nhiệt độ, độ ẩm, ánh sáng và lưu ý an toàn.\n\n"
        "QUY TẮC TRÍCH DẪN NOTEBOOKLM:\n"
        "- Chèn ký hiệu trích dẫn dạng số trong ngoặc vuông như [1], [2] ngay sau các luận điểm chuyên môn quan trọng, liều dùng, chỉ định, chống chỉ định tương ứng với số thứ tự trong Context.\n"
        "- Nếu thông tin thuộc kiến thức dược lý chuẩn mực không có trong Context, vẫn trình bày đầy đủ chính xác và có thể trích dẫn nguồn chuẩn y văn tổng quát.\n\n"
        "YÊU CẦU ĐẦU RA LÀ JSON OBJECT VỚI SCHEMA:\n"
        "{\n"
        "  \"drug_name\": \"Tên thuốc (Tên hoạt chất / Biệt dược chính)\",\n"
        "  \"subtitle\": \"Mô tả ngắn gọn nhóm dược lý\",\n"
        "  \"confidence_overall\": \"Cao\",\n"
        "  \"quick_summary\": [\n"
        "    { \"type\": \"success\", \"text\": \"Điểm tích cực / hiệu quả chính\" },\n"
        "    { \"type\": \"success\", \"text\": \"Tính an toàn khi đúng liều\" },\n"
        "    { \"type\": \"warning\", \"text\": \"Cảnh báo quá liều hoặc tác dụng phụ cần lưu ý\" },\n"
        "    { \"type\": \"danger\", \"text\": \"Chống chỉ định hoặc tương tác cấm tuyệt đối\" }\n"
        "  ],\n"
        "  \"sections\": [\n"
        "    { \"id\": \"1\", \"title\": \"1. Tổng quan\", \"confidence\": \"Cao\", \"content\": \"...\" },\n"
        "    { \"id\": \"2\", \"title\": \"2. Chỉ định\", \"confidence\": \"Cao\", \"content\": \"...\" },\n"
        "    { \"id\": \"3\", \"title\": \"3. Liều dùng\", \"confidence\": \"Cao\", \"content\": \"...\" },\n"
        "    { \"id\": \"4\", \"title\": \"4. Chống chỉ định\", \"confidence\": \"Cao\", \"content\": \"...\" },\n"
        "    { \"id\": \"5\", \"title\": \"5. Tác dụng phụ\", \"confidence\": \"Cao\", \"content\": \"...\" },\n"
        "    { \"id\": \"6\", \"title\": \"6. Tương tác thuốc\", \"confidence\": \"Cao\", \"content\": \"...\" },\n"
        "    { \"id\": \"7\", \"title\": \"7. Thận trọng\", \"confidence\": \"Cao\", \"content\": \"...\" },\n"
        "    { \"id\": \"8\", \"title\": \"8. Dạng bào chế\", \"confidence\": \"Cao\", \"content\": \"...\" },\n"
        "    { \"id\": \"9\", \"title\": \"9. Bảo quản\", \"confidence\": \"Cao\", \"content\": \"...\" }\n"
        "  ]\n"
        "}\n"
        "Không xuất thêm bất kỳ văn bản giải thích nào ngoài JSON."
    )

    user_prompt = f"Yêu cầu tra cứu thuốc/nhóm thuốc: {query}\n\n"
    if context_str:
        user_prompt += f"Ngữ cảnh trích xuất từ tài liệu y văn (Context):\n{context_str}\n\n"
    user_prompt += "Hãy tạo Bản Báo Cáo Dược Lý Chi Tiết định dạng JSON theo đúng schema."

    client = _llm_client(api_key)
    response = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_tokens=3500,
        response_format={"type": "json_object"}
    )
    content = _strip_json_fences(response.choices[0].message.content)
    parsed = json.loads(content)

    return {
        "drug_name": str(parsed.get("drug_name") or query),
        "subtitle": str(parsed.get("subtitle") or "Dữ liệu thông tin dược lý"),
        "confidence_overall": str(parsed.get("confidence_overall") or "Cao"),
        "quick_summary": parsed.get("quick_summary") or [],
        "sections": parsed.get("sections") or [],
        "sources_meta": sources_meta
    }


# =============================================================================
# Tra cứu thuốc: bản STREAMING
#
# Bản blocking `generate_drug_report` ở trên dùng response_format=json_object
# với max_tokens=3500, nên bác sĩ nhìn màn hình trắng suốt ~18,7s cho tới khi
# JSON sinh xong mới parse được. Đo trên DeepSeek: TTFT 0,52s, ~106 tok/s —
# gần như toàn bộ thời gian chờ đó là chờ vô ích.
#
# JSON mode không stream từng phần được (JSON dở dang thì json.loads hỏng),
# nên bản này đổi sang định dạng phân tách bằng "@@" — parse lại được ở bất
# kỳ điểm cắt nào. Hàm trả về generator sinh ra snapshot ĐÚNG schema mà giao
# diện đang render, để frontend chỉ việc thay state.
# =============================================================================

DRUG_STREAM_SYSTEM_PROMPT = (
    "Bạn là Chuyên gia Dược học Lâm sàng (Clinical Pharmacologist) và Cố vấn Y khoa cao cấp.\n"
    "Hãy lập Bản Báo Cáo Y Khoa Toàn Diện về thuốc hoặc nhóm thuốc được yêu cầu.\n\n"
    "ĐỊNH DẠNG ĐẦU RA BẮT BUỘC — chỉ dùng các dòng lệnh bắt đầu bằng @@, không xuất gì khác:\n"
    "@@NAME|<Tên hoạt chất / Biệt dược chính>\n"
    "@@SUBTITLE|<Mô tả ngắn nhóm dược lý>\n"
    "@@CONFIDENCE|<Cao hoặc Trung bình hoặc Thấp>\n"
    "@@SEC|<số>|<tiêu đề mục>|<độ tin cậy>\n"
    "<nội dung mục, có thể nhiều dòng, dùng gạch đầu dòng>\n"
    "... (lặp đủ 9 mục @@SEC) ...\n"
    "@@SUM|success|<Điểm hiệu quả chính>\n"
    "@@SUM|success|<Tính an toàn khi đúng liều>\n"
    "@@SUM|warning|<Cảnh báo quá liều hoặc tác dụng phụ cần lưu ý>\n"
    "@@SUM|danger|<Chống chỉ định hoặc tương tác cấm tuyệt đối>\n\n"
    "THỨ TỰ BẮT BUỘC: ba dòng NAME/SUBTITLE/CONFIDENCE thật ngắn, rồi ĐI THẲNG\n"
    "vào @@SEC|1. Bốn dòng @@SUM đặt ở CUỐI CÙNG, sau mục 9. Lý do: báo cáo\n"
    "được phát theo luồng để bác sĩ đọc ngay khi chữ vừa sinh ra, nên phần nội\n"
    "dung phải đến trước phần tóm tắt.\n\n"
    "PHẢI có ĐÚNG 9 mục @@SEC theo thứ tự:\n"
    "1. Tổng quan - Định nghĩa hoạt chất, nhóm dược lý, cơ chế tác dụng.\n"
    "2. Chỉ định - Bệnh lý, hội chứng được phép điều trị.\n"
    "3. Liều dùng - Phân chia rõ Người lớn và Trẻ em, khoảng cách liều, liều tối đa.\n"
    "4. Chống chỉ định - Trường hợp tuyệt đối hoặc tương đối không được dùng.\n"
    "5. Tác dụng phụ - Phân loại thường gặp, ít gặp, nghiêm trọng.\n"
    "6. Tương tác thuốc - Cặp tương tác quan trọng (thuốc, thức ăn, rượu).\n"
    "7. Thận trọng - Suy gan/thận, người cao tuổi, phụ nữ có thai và cho con bú.\n"
    "8. Dạng bào chế - Dạng thuốc và hàm lượng thông dụng.\n"
    "9. Bảo quản - Nhiệt độ, độ ẩm, ánh sáng, lưu ý an toàn.\n\n"
    "TRÍCH DẪN: chèn [1], [2] ngay sau các luận điểm chuyên môn, liều dùng, chỉ định, "
    "chống chỉ định - số tương ứng với thứ tự nguồn trong Context. Nếu là kiến thức dược lý "
    "chuẩn mực không có trong Context, vẫn trình bày đầy đủ chính xác.\n\n"
    "TUYỆT ĐỐI không xuất JSON, không xuất markdown code fence, không giải thích thêm.\n"
    "Không dùng ký tự sổ dọc bên trong nội dung mục."
)


def _blank_drug_report(query: str) -> Dict[str, Any]:
    return {
        "drug_name": query,
        "subtitle": "Đang tổng hợp dữ liệu dược lý...",
        "confidence_overall": "Cao",
        "quick_summary": [],
        "sections": [],
    }


def _parse_drug_stream_buffer(buffer: str, query: str) -> Dict[str, Any]:
    """Dựng lại báo cáo từ buffer, kể cả khi buffer đang dở dang.

    Gọi được ở bất kỳ điểm cắt nào của luồng: dòng cuối chưa hoàn chỉnh vẫn
    được đưa vào nội dung mục đang mở, để chữ chạy mượt trên giao diện.
    """
    report = _blank_drug_report(query)
    lines = buffer.split("\n")
    current = None

    for i, line in enumerate(lines):
        is_last_partial = (i == len(lines) - 1) and not buffer.endswith("\n")

        if line.startswith("@@"):
            # Dòng lệnh dở dang ở cuối luồng: bỏ qua, chờ chunk sau.
            if is_last_partial and "|" not in line:
                continue
            parts = line[2:].split("|")
            tag = parts[0].strip().upper()

            if tag == "NAME" and len(parts) > 1:
                report["drug_name"] = parts[1].strip() or query
            elif tag == "SUBTITLE" and len(parts) > 1:
                report["subtitle"] = parts[1].strip()
            elif tag == "CONFIDENCE" and len(parts) > 1:
                report["confidence_overall"] = parts[1].strip() or "Cao"
            elif tag == "SUM" and len(parts) > 2:
                kind = parts[1].strip().lower()
                if kind not in ("success", "warning", "danger", "info"):
                    kind = "info"
                text = "|".join(parts[2:]).strip()
                if text:
                    report["quick_summary"].append({"type": kind, "text": text})
            elif tag == "SEC" and len(parts) > 2:
                current = {
                    "id": parts[1].strip(),
                    "title": parts[2].strip(),
                    "confidence": parts[3].strip() if len(parts) > 3 else "Cao",
                    "content": "",
                }
                report["sections"].append(current)
            continue

        if current is not None:
            current["content"] += line if not current["content"] else "\n" + line

    for sec in report["sections"]:
        sec["content"] = sec["content"].strip()
    return report


def stream_drug_report(query, context_chunks, custom_api_key=""):
    """Sinh báo cáo tra cứu thuốc theo luồng.

    Yield ra các tuple (event, payload):
      ("update", <báo cáo dạng dict>)  - snapshot, phát nhiều lần
      ("error",  <chuỗi thông báo>)    - hỏng giữa chừng
    """
    api_key = custom_api_key if custom_api_key else config.DEEPSEEK_API_KEY
    if not api_key:
        yield ("error", "DeepSeek API key chưa được cấu hình. Vui lòng cấu hình "
                        "API Key trong mục Cài đặt hoặc file .env.")
        return

    context_str = ""
    for idx, chunk in enumerate(context_chunks):
        cite_id = idx + 1
        doc_name = chunk.get("doc_name", "")
        page_num = chunk.get("page_num", 1)
        page_label = page_num if str(page_num).startswith("Trang") else f"Trang {page_num}"
        context_str += (f"[{cite_id}] Tài liệu: {doc_name} ({page_label})\n"
                        f"Nội dung: {chunk.get('text', '')}\n\n")

    user_prompt = f"Yêu cầu tra cứu thuốc/nhóm thuốc: {query}\n\n"
    if context_str:
        user_prompt += f"Ngữ cảnh trích xuất từ tài liệu y văn (Context):\n{context_str}\n\n"
    user_prompt += "Hãy tạo Bản Báo Cáo Dược Lý Chi Tiết theo đúng định dạng @@ đã quy định."

    buffer = ""
    last_emitted_len = 0
    try:
        client = _llm_client(api_key)
        stream = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": DRUG_STREAM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            # 6000 chu khong phai 3500: dinh dang @@ dai hon JSON (khong nen
            # escape nhung xuong dong that), va 4 dong @@SUM nam o CUOI nen
            # chung la thu bi cat dau tien khi cham tran. Do tren amoxicillin:
            # 3500 token cat mat toan bo phan tom tat.
            max_tokens=6000,
            stream=True,
        )
        finish_reason = None
        for chunk in stream:
            if not chunk.choices:
                continue
            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason
            delta = chunk.choices[0].delta.content
            if not delta:
                continue
            buffer += delta
            # Phát snapshot khi đủ chữ mới hoặc vừa xong một dòng: giảm số lần
            # parse lại mà mắt vẫn thấy chữ chạy liên tục.
            if len(buffer) - last_emitted_len >= 48 or delta.endswith("\n"):
                last_emitted_len = len(buffer)
                yield ("update", _parse_drug_stream_buffer(buffer, query))
        if finish_reason == "length":
            # Báo ra log thay vì im lặng cắt mất mục: nếu thấy dòng này thường
            # xuyên thì phải nâng max_tokens hoặc rút ngắn ngữ cảnh đầu vào.
            print(f"[DRUG] Cảnh báo: báo cáo '{query}' bị cắt do chạm trần token.")
    except Exception as e:
        print(f"Lỗi khi stream báo cáo thuốc: {e}")
        if not buffer:
            yield ("error", f"Không thể tạo báo cáo tra cứu thuốc: {e}")
            return

    yield ("update", _parse_drug_stream_buffer(buffer, query))
