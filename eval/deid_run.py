# -*- coding: utf-8 -*-
"""
Bất biến của đợt 3: tên bệnh nhân KHÔNG BAO GIỜ rời khỏi máy này.

Chạy:  python eval/deid_run.py       (thoát 1 nếu hỏng)

Vì sao là phép thử tự động chứ không phải một lần chạy tay: kho này không có
test React nào, lưới an toàn chỉ gồm ba lệnh, và đây là thứ duy nhất phải hỏng
THÀNH TIẾNG chứ không được hỏng im lặng. Chạy tay thì kiểm được một lần; cái
này kiểm được mọi lần sau.

Phép thử KHÔNG chạm vào cơ sở dữ liệu thật và KHÔNG gọi ra mạng:
  - patient_db.get_patient bị thay bằng một hồ sơ giả, nên bệnh án thật của bác
    sĩ không bị đụng tới.
  - _llm_client bị thay bằng một bộ ghi, nên mọi payload lẽ ra gửi ra DeepSeek
    đều bị giữ lại ở đây để soi, và không có byte nào rời khỏi máy.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import patient_db  # noqa: E402

# Các dấu hiệu định danh. Chọn chuỗi lạ để không thể trùng ngẫu nhiên với chữ
# tiếng Việt bình thường trong prompt.
NAME = "ZZQUACHTHITESTNAME"
CODE = "ZZBN999999"
PHONE = "0900000ZZZ"
EMAIL = "zz-test@example.invalid"
ADDRESS = "ZZSONHA 12, ZZPHUONGTEST"
ALLERGY = "Dị ứng penicillin, nổi mề đay toàn thân"
IDENTIFIERS = [NAME, CODE, PHONE, EMAIL, ADDRESS]

FAKE_PATIENT = {
    "id": "zz-test-id", "code": CODE, "name": NAME,
    "dob": "1990-04-11", "age": 36, "gender": "Nam",
    "phone": PHONE, "email": EMAIL, "address": ADDRESS, "occupation": "ZZNGHETEST",
    "allergies": ALLERGY,
    "chronic_conditions": "Hen phế quản",
    "surgical_history": "", "family_history": "",
    "visits": [{"visit_date": "2026-03-14", "symptoms": "ho kéo dài",
                "diagnosis_primary": "Viêm phế quản cấp (J20)"}],
    "vitals": [{"vital_type": "Mạch", "value": "88 l/p"}],
    "notes": [{"visit_date": "2026-03-14", "reason_for_visit": "khám lại sau đợt ho"}],
}

patient_db.get_patient = lambda pid: FAKE_PATIENT if pid == "zz-test-id" else None

import patient_context  # noqa: E402
import llm_client  # noqa: E402
import agent  # noqa: E402

failures = []
checks = 0


def check(ok, label):
    global checks
    checks += 1
    if not ok:
        failures.append(label)
    print(("  ok   " if ok else "  HỎNG ") + label)


# ---------------------------------------------------------------- 1. chuỗi tiền sử
print("\n[1] Chuỗi tiền sử dựng ra")
ctx = patient_context.build_patient_context("zz-test-id")
for ident in IDENTIFIERS:
    check(ident not in ctx, f"không chứa định danh {ident[:14]}…")
check("penicillin" in ctx.lower(), "CÓ chứa dị ứng penicillin")
check("36 tuổi" in ctx, "giữ lại tuổi (có ý nghĩa lâm sàng)")
check("Nam" in ctx, "giữ lại giới tính")
check("2026-03-14" in ctx, "giữ lại mốc thời gian khám")
check(patient_context.build_patient_context(None) is None, "không có bệnh nhân -> None")


# ---------------------------------------------------------------- 2. bộ ghi payload
sent = []


class _Msg:
    content = json.dumps({
        "root": {"id": "n0", "label": "x", "children": []},
        "diagnosis_primary": "Viêm họng cấp (J02)", "diagnosis_differentials": [],
        "reasoning": "thử", "diagnoses": [], "regions": [], "maneuvers": [], "signs": [],
        "medications": [], "no_drug_recommendations": "", "care_instructions": "",
        "goals": [], "protocol_duration": "", "treatment_method": "",
        "diet_regimen": "", "precautions": "",
    }, ensure_ascii=False)
    tool_calls = None


class _Recorder:
    class chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                sent.append(kwargs.get("messages") or [])
                class R:
                    choices = [type("C", (), {"message": _Msg()})()]
                return R()


llm_client._llm_client = lambda *a, **k: _Recorder()
agent._llm_client = lambda *a, **k: _Recorder()

_, block = patient_context.build_prompt_block("zz-test-id")

CALLS = [
    ("generate (bước 1)", lambda: llm_client.generate_diagnosis_tree(
        "Nam 36 tuổi, đau họng", "sk-zz", patient_block=block)),
    ("endoscopy (bước 2)", lambda: llm_client.suggest_endoscopy_exam(
        ["đau họng"], [], "sk-zz", patient_block=block)),
    ("final (bước 3)", lambda: llm_client.generate_final_diagnosis(
        ["đau họng"], [], "nội soi họng đỏ", "sk-zz", patient_block=block)),
    ("treatment (bước 4)", lambda: llm_client.generate_treatment_suggestion(
        [{"disease_name": "Viêm họng cấp"}], "nội soi họng đỏ", "sk-zz", patient_block=block)),
    ("agent chẩn đoán", lambda: agent.run_diagnostic_agent(
        "zz-test-id", "đau họng, sốt", lambda q: [], "sk-zz")),
]

print("\n[2] Payload thật sự gửi ra DeepSeek")
for label, fn in CALLS:
    sent.clear()
    try:
        fn()
    except Exception as e:                      # parser có thể không nuốt JSON giả
        print(f"  (bỏ qua lỗi phân tích ở {label}: {type(e).__name__})")
    check(len(sent) > 0, f"{label}: có gửi đi ít nhất một lượt")
    blob = json.dumps(sent, ensure_ascii=False)
    for ident in IDENTIFIERS:
        check(ident not in blob, f"{label}: không rò {ident[:14]}…")
    check("penicillin" in blob.lower(), f"{label}: dị ứng CÓ tới được mô hình")


# ---------------------------------------------------------------- 3. không có bệnh nhân
print("\n[3] Không chọn bệnh nhân -> prompt như cũ")
sent.clear()
_, empty_block = patient_context.build_prompt_block(None)
check(empty_block == "", "khối tiền sử rỗng")
try:
    llm_client.generate_diagnosis_tree("Nam 28 tuổi, sốt", "sk-zz", patient_block=empty_block)
except Exception:
    pass
blob = json.dumps(sent, ensure_ascii=False)
check(patient_context.CONTEXT_TAG not in blob, "không chèn thẻ tiền sử rỗng vào prompt")


print(f"\n{checks - len(failures)}/{checks} đạt")
if failures:
    print("\nHỎNG:")
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("Tên bệnh nhân không rời khỏi máy này.")
