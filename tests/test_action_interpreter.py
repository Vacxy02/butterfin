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

# ---------------------------------------------------------------------------
# 은행/상품명 감지 (2026-08-28 추가) — demo_rules.json에 실제로 등록된 기관만
# institution으로 채워지는지, 등록 안 된/일반 단어는 오탐하지 않는지 검증.
# ---------------------------------------------------------------------------
d6, _ = interpret("신협 적금 때문에 급여계좌 옮기려고", force_mock=True)
check("문장에 '신협' 언급 → institution=신협", d6.institution == "신협")

d7, _ = interpret("케이뱅크 통신비 자동이체 해야돼서 계좌 변경하려고", force_mock=True)
check("문장에 '케이뱅크' 언급 → institution=케이뱅크", d7.institution == "케이뱅크")

d8, _ = interpret("하나은행 적금 해지할까 고민중이야", force_mock=True)
check("문장에 '하나은행' 언급 → institution=하나은행", d8.institution == "하나은행")

d9, _ = interpret("주택청약 하나 해지하려고", force_mock=True)
check("'하나'라는 일반 단어만 있고 '하나은행'이 아님 → institution 오탐 안 함(None)",
      d9.institution is None)

d10, _ = interpret("다음 달부터 카드사용 5만원을 다른 카드로 옮길 거야", force_mock=True)
check("은행명이 아예 없는 문장 → institution=None (지어내지 않음)", d10.institution is None)

d11, _ = interpret("디딤돌대출 때문에 청약통장 해지 안 하려고 해", force_mock=True)
check("별칭('디딤돌대출')으로도 정식 명칭(주택금융공사)을 찾음", d11.institution == "주택금융공사")

# ---------------------------------------------------------------------------
# 상품명 감지 (2026-08-28 추가) — 은행명만으로는 상품을 특정할 수 없다는 지적을
# 반영해서, institution과 완전히 독립적으로 product도 감지되는지 검증.
# ---------------------------------------------------------------------------
d12, _ = interpret("디딤돌대출 때문에 청약통장 해지 안 하려고 해", force_mock=True)
check("'디딤돌대출' 한 단어로 institution과 product가 각각 채워짐(둘 다 독립적으로 감지)",
      d12.institution == "주택금융공사" and d12.product == "내집마련 디딤돌대출")

d13, _ = interpret("오늘부터 하나 적금 해지할까 고민중이야", force_mock=True)
check("띄어쓰기가 다른 표현('하나 적금')도 정식 명칭(오늘부터, 하나 적금)을 찾음",
      d13.product == "오늘부터, 하나 적금" and d13.institution == "하나은행")

d14, _ = interpret("자유적금 때문에 계좌 옮겨야 해서 결제계좌 변경하려고", force_mock=True)
check("은행명 언급 없이 상품명만으로도 product가 채워짐(institution은 못 찾아 None)",
      d14.product == "주거래우대 자유적금" and d14.institution is None)

d15, _ = interpret("신협 카드실적 5만원 다른 카드로 옮길 거야", force_mock=True)
check("은행명만 있고 상품명이 없는 문장 → institution만 채워지고 product는 None (상품명을 억지로 추측 안 함)",
      d15.institution == "신협" and d15.product is None)

d16, _ = interpret("그냥 아무 은행 카드 5만원 옮길 거야", force_mock=True)
check("은행/상품명이 전혀 없는 문장 → 둘 다 None", d16.institution is None and d16.product is None)

# rule_store.match()가 institution과 product를 각각 독립적으로 좁히는지도 여기서
# 통합 검증한다(app.py 실제 사용 형태와 동일하게).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mvp"))
from rule_store import RuleStore
_store = RuleStore()

only_product = _store.match("PAYMENT_ACCOUNT_CHANGE", product="주거래우대 자유적금")
check("product만 줘도 정확히 좁혀짐 (KBANK_TELECOM_SAVINGS 하나만)",
      [r["rule_id"] for r in only_product] == ["KBANK_TELECOM_SAVINGS"])

both = _store.match("PRODUCT_TERMINATION", institution="주택금융공사", product="내집마련 디딤돌대출")
check("institution+product 둘 다 줘도 정확히 좁혀짐 (HF_SUBSCRIPTION_DIDIMDOL 하나만)",
      [r["rule_id"] for r in both] == ["HF_SUBSCRIPTION_DIDIMDOL"])

fake_product = _store.match("CARD_SPEND_SHIFT", product="존재하지않는상품명")
check("존재하지 않는 product를 줘도 0건이 아니라 전체 후보로 안전하게 fallback",
      len(fake_product) > 0)

# ---------------------------------------------------------------------------
# 2026-09-05 (FINAL_HARDENING Red-Team, P0-4): 실제 라이브(OpenAI)에서 "적금 하나
# 해지하려고 해"처럼 기관/상품이 특정 안 된 문장에 status="UNSUPPORTED"이면서
# action_type="PRODUCT_TERMINATION"을 같이 채우는 모순 응답이 재현됐다. 이 상태를
# 그대로 두면 화면이 action_type을 자동 채워 넣고, institution/product 없이
# evaluate가 rule_store의 "전체 후보 fallback"으로 임의의 규칙을 골라 확정 판정
# (HOLD 등)까지 내려버린다 — 사용자가 지정한 적 없는 상품에 대한 그럴듯한 오판.
# _double_check()가 이 모순을 무조건 걸러내는지 직접 검증한다(mock/실제 provider
# 여부와 무관하게 항상 적용되는 방어선이므로 함수를 직접 호출해서 검증).
from action_interpreter import _double_check

contradictory = {"status": "UNSUPPORTED", "action_type": "PRODUCT_TERMINATION",
                 "amount_monthly": None, "direct_benefit_monthly": None, "clarifying_question": None}
fixed = _double_check(contradictory)
check("P0-4: status=UNSUPPORTED + action_type 동시 존재(AI 모순 응답) → action_type을 무조건 제거",
      fixed["action_type"] is None and fixed["status"] == "UNSUPPORTED")

print(f"\n{passed} passed, {failed} failed")
if failed:
    raise SystemExit(1)
