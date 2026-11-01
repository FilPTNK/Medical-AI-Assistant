"""Chấm quy tắc hồi quy WP6 trên văn bản/JSON DeepSeek đã lưu; không gọi API.

Dùng: python eval/wp6_grade.py eval/wp6_cases.json path/to/outputs.json
outputs.json là object {case_id: "câu trả lời"} hoặc {case_id: object JSON đầu ra}.
Trả mã thoát 1 nếu bất kỳ ca nào không đạt; không thay thế kiểm định y khoa.
"""
import json
import re
import sys
from pathlib import Path

# Cùng một bộ bóc liều với cổng số liệu lúc chạy (backend/answer_verify.py), để
# chấm ngoại tuyến và kiểm trực tuyến không bao giờ lệch nhau.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import answer_verify  # noqa: E402

CITATION = re.compile(r"\[(\d+)\]")
ABSTENTION = re.compile(r"nguồn\s+không\s+đề\s+cập", re.I)


def grade(case, output):
    """Trả danh sách lỗi; kiểm chứng số trích dẫn, không suy luận tính phù hợp ngữ nghĩa."""
    answer = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    context = case['context']
    errors = []
    cited = [int(n) for n in CITATION.findall(answer)]
    invalid = [n for n in cited if n < 1 or n > len(context)]
    if invalid:
        errors.append(f"Trích dẫn ngoài phạm vi: {invalid}")
    if case['expect']['citation_required'] and not cited:
        errors.append("Thiếu trích dẫn [n]")
    if case['expect']['abstention_required'] and not ABSTENTION.search(answer):
        errors.append("Thiếu 'Nguồn không đề cập'")
    # Liều có ở nguồn KHÁC nguồn được trích vẫn tính là có căn cứ ở đây — bộ chấm
    # này chỉ bắt con số bịa; lúc chạy, giao diện vẫn báo trích nhầm nguồn.
    flags = answer_verify.verify_answer(answer, context)['flags']
    ungrounded = sorted({f['text'] for f in flags if f['status'] in ('ungrounded', 'unit_mismatch')})
    if ungrounded:
        errors.append(f"Liều có đơn vị không thấy trong nguồn: {ungrounded}")
    return errors


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    cases = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    outputs = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
    failed = 0
    for case in cases:
        if case['id'] not in outputs:
            errors = ['Thiếu đầu ra cho ca kiểm thử']
        else:
            errors = grade(case, outputs[case['id']])
        failed += bool(errors)
        print(f"{case['id']}: {'; '.join(errors) if errors else 'OK'}")
    return int(bool(failed))


if __name__ == '__main__':
    sys.exit(main())
