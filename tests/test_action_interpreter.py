"""action_interpreter.py 테스트 (mock 모드 — GEMINI_API_KEY 없이 실행).

2026-08-25: mvp/rule_compiler.py는 팀의 실제 ai_rule.py가 도착하면서 폐기했다
(evidence_schema_gate 등 존재하지 않는 옛 API에 의존해 깨져 있었고, System B/C 역할은
ablation/wide_compiler.py가 대신한다 — mvp/app.py 라이브 데모도 rule_compiler를 쓰지
않았으므로 안전하게 제거). 이 파일은 그중 여전히 유효하고 app.py가 실제로 쓰는
action_interpreter.py만 남긴 것이다."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mvp"))

from action_interpreter import interpret

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        print(f"✅ {name}")
        passed += 1
    else:
        print(f"❌ {name}")
        failed += 1


d1, _ = interpret("다음 달부터 카드사용 5만원을 다른 카드로 옮길 거야", force_mock=True)
check("카드 이동 문장 → OK", d1.status == "OK")
check("카드 이동 문장 → action_type=CARD_SPEND_SHIFT", d1.action_type == "CARD_SPEND_SHIFT")
check("카드 이동 문장 → amount_monthly=50000", d1.amount_monthly == 50000)

d2, _ = interpret("청약통장 해지하려고 해", force_mock=True)
check("청약통장 해지 → PRODUCT_TERMINATION", d2.action_type == "PRODUCT_TERMINATION")

d3, _ = interpret("카드를 다른 카드로 옮길 거야", force_mock=True)  # 금액 없음
check("금액 없는 카드 이동 → NEED_INFO", d3.status == "NEED_INFO")
check("NEED_INFO → clarifying_question 존재", bool(d3.clarifying_question))

d4, _ = interpret("오늘 날씨 어때", force_mock=True)
check("무관한 문장 → UNSUPPORTED", d4.status == "UNSUPPORTED")

d5, _ = interpret("", force_mock=True)
check("빈 입력 → NEED_INFO", d5.status == "NEED_INFO")

print(f"\n{passed} passed, {failed} failed")
if failed:
    raise SystemExit(1)
