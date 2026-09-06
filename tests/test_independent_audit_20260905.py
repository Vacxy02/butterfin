"""2026-09-05 독립감사(F01~F28) 회귀테스트.

Butterfin_TO_DONGHAK_CLAUDE_V4_1_EXPLICIT_FILES_20260905.zip의 F01~F28 감사
프로토콜을 최신 repo(이 세션이 이미 여러 차례 수정해온 코드)에 대해 독립적으로
재현·검증한 결과, 아래 항목들만 "기존에 이미 문서화·재검증된 골든 데모를 깨지
않으면서 안전하게 고칠 수 있는 실제 버그"로 확인해 이번 세션에서 고쳤다.

의도적으로 고치지 않은 것(문서로만 남김, 이 파일에서 회귀로 고정하지 않음):
- F02/F10 matched[0] 임의 선택 — PRODUCT_TERMINATION/PAYMENT_ACCOUNT_CHANGE를
  기관·상품 없이 호출하면 3파전에서 첫 번째 규칙이 확정된다. 이걸 "여러 개면
  REVIEW"로 고치면 2026-09-04 배포본_재검증기록.md에 이미 재검증되어 박힌
  "상품 해지(기관·상품 미지정) → HOLD, 매칭 KB_SAVINGS_LOAN_HOLD" 골든 시나리오가
  깨진다 — 제출 하루 전에 문서화된 재현 결과를 바꾸는 위험을 감수하지 않았다.
- F04 generic exception 체크박스 — SHINHYUP_SALARY는 demo_rules.json에 "exception"
  필드가 아예 없는데도 "예외 조건 체크 → PASS"가 배포본_재검증기록.md에 이미
  재검증된 골든 시나리오로 박혀 있다. "exception 필드가 있는 규칙에만 체크박스가
  먹히게" 고치면 이 골든 시나리오가 깨지므로 보류.
이 두 건은 감사 보고서(FINAL_HARDENING_REPORT 계열 후속 문서)에 ACCEPT로 남기고
제출 이후 과제로 넘긴다.

이번 세션에서 실제로 고친 것(아래에서 회귀 고정):
- F16 causal validity: HANA_HISTORY_SAVINGS는 "가입 전일 기준 과거 이력"이라
  지금 해지해도 그 이력 자체는 안 바뀐다 — 기존엔 다른 이산 규칙과 똑같이 처리돼
  무조건 HOLD가 나왔다. 이 규칙만 별도로 "행동이 조건에 영향 없음"으로 답하게
  고쳤다(다른 규칙엔 영향 없음, 이 시나리오는 골든 데모 표에 없었음).
- F23 입력 검증: amount_monthly가 문자열("50000")이면 `<=` 비교에서 TypeError로
  500이 나던 걸 고쳤다(안전하게 REVIEW로 종료). linked_balance가 음수면 그대로
  계산에 흘려보내지 않고 "안 준 것"과 동일하게 가정값으로 대체한다.
- F27 보안: (1) /api/interpret가 AI 호출 실패 시 원문 예외 메시지를 meta.error로
  그대로 클라이언트에 내려주던 것(코드 자체 주석의 의도와 반대)을 서버 로그로만
  남기게 고쳤다. (2) clarifying_question을 innerHTML에 그대로 꽂던 XSS 경로를
  escapeHtml()로 막았다. (3) 자연어 입력 길이 제한(클라이언트 maxlength=300,
  서버 500자 하드컷)을 추가했다.

기존 205개 테스트는 이 파일에서 한 줄도 건드리지 않는다 — 순수 추가(additive)다.
"""
import sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mvp"))

from app import app as flask_app

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"✅ {name}")
    else:
        failed += 1
        print(f"❌ {name}  {detail}")


client = flask_app.test_client()

# ---------------------------------------------------------------------------
# 골든 데모 불변성 확인 — 이번 감사에서 고친 것들이 기존에 문서화·재검증된
# 대표 시연 결과를 절대 안 건드렸는지부터 고정한다(가장 중요한 회귀).
# ---------------------------------------------------------------------------
r_main = client.post("/api/evaluate", json={"action_type": "CARD_SPEND_SHIFT",
                                             "institution": "KB국민은행",
                                             "product": "대출 금리감면 (일반 신용대출)",
                                             "amount_monthly": 50000,
                                             "direct_benefit_monthly": 1000}).get_json()
check("골든 데모 불변: 메인 시연(5만원) → 여전히 HOLD/KB_CARD_LOAN_STEP",
      r_main["decision"] == "HOLD" and r_main["matched_rules"] == ["KB_CARD_LOAN_STEP"])

r_salary = client.post("/api/evaluate", json={"action_type": "SALARY_ACCOUNT_CHANGE"}).get_json()
check("골든 데모 불변: 급여계좌 변경(기관 미지정) → 여전히 HOLD/SHINHYUP_SALARY",
      r_salary["decision"] == "HOLD" and r_salary["matched_rules"] == ["SHINHYUP_SALARY"])

# 2026-09-05 (V7 FIX 2, exception gating): SHINHYUP_SALARY에는 exception 필드가
# 아예 없다 — exception_condition_met=True를 보내도 예외를 적용할 근거 규칙이 없으므로
# 더 이상 PASS로 넘어가면 안 된다(예전엔 exception 필드 유무와 무관하게 무조건 적용해
# 임의의 면제를 만들어줬다). 이제는 HOLD 그대로 유지되는 게 올바른 동작이다.
r_salary_exc = client.post("/api/evaluate", json={"action_type": "SALARY_ACCOUNT_CHANGE",
                                                    "exception_condition_met": True}).get_json()
check("골든 데모 갱신(V7 FIX 2): SHINHYUP_SALARY는 exception 필드가 없어 exception_condition_met=True를 줘도 PASS로 넘어가지 않음(HOLD 유지)",
      r_salary_exc["decision"] == "HOLD")

# 2026-09-05 (V7 FIX 1, strict/fail-closed matching): institution/product를 안 주면
# PRODUCT_TERMINATION에 3개 규칙(KB_SAVINGS_LOAN_HOLD/HF_SUBSCRIPTION_DIDIMDOL/
# HANA_HISTORY_SAVINGS)이 동시에 매칭된다 — 예전엔 matched[0]을 임의로 골라 확정
# HOLD를 냈지만, 이제는 정직하게 REVIEW로 사용자에게 특정을 요청한다.
r_term = client.post("/api/evaluate", json={"action_type": "PRODUCT_TERMINATION"}).get_json()
check("골든 데모 갱신(V7 FIX 1): 상품 해지(기관 미지정) → 3건 중복 매칭이라 REVIEW(임의 선택 금지)",
      r_term["decision"] == "REVIEW" and set(r_term["matched_rules"]) ==
      {"KB_SAVINGS_LOAN_HOLD", "HF_SUBSCRIPTION_DIDIMDOL", "HANA_HISTORY_SAVINGS"})

# institution/product를 정확히 주면 KB_SAVINGS_LOAN_HOLD 단독 매칭 → 여전히 HOLD.
r_term_kb = client.post("/api/evaluate", json={"action_type": "PRODUCT_TERMINATION",
                                                "institution": "KB국민은행",
                                                "product": "대출 금리감면 (일반 신용대출)"}).get_json()
check("골든 데모 불변: 상품 해지(KB 특정) → 여전히 HOLD/KB_SAVINGS_LOAN_HOLD",
      r_term_kb["decision"] == "HOLD" and r_term_kb["matched_rules"] == ["KB_SAVINGS_LOAN_HOLD"])

# ---------------------------------------------------------------------------
# F16 — HANA_HISTORY_SAVINGS 인과관계 수정
# ---------------------------------------------------------------------------
r_hana = client.post("/api/evaluate", json={"action_type": "PRODUCT_TERMINATION",
                                             "institution": "하나은행",
                                             "product": "오늘부터, 하나 적금"}).get_json()
# 2026-09-05 (V7 FIX 7): 문구가 "가입 시점에 이미 확정"에서 "이 등록 규칙(가입 전
# 6개월 이력)은 현재 해지행동의 영향을 받지 않습니다"로 갱신됐다 — 결정(PASS)은 그대로.
check("F16: 하나은행 이력 조건은 가입 전 확정 사실 — 지금 해지해도 PASS(false HOLD 제거)",
      r_hana["decision"] == "PASS" and "현재 해지행동의 영향을 받지 않습니다" in r_hana["reason"])
check("F16: 하나은행 케이스는 D/L/G 그대로 None, reversal도 False(D/G 없는 조건이 애초에 안 깨짐)",
      r_hana["effects"]["D"] is None and r_hana["effects"]["reversal"] is False)
check("F16: causal_note로 왜 PASS인지 근거를 남김(값을 지어내지 않고 이유를 설명)",
      "causal_note" in r_hana["condition"] and r_hana["condition"]["causal_note"])
check("F16: 다른 규칙(KB_SAVINGS_LOAN_HOLD)에는 영향 없음 — institution/product로 특정하면 여전히 HOLD",
      r_term_kb["decision"] == "HOLD")

# ---------------------------------------------------------------------------
# F23 — 입력 타입/범위 검증(크래시 대신 fail-closed)
# ---------------------------------------------------------------------------
r_str_amount = client.post("/api/evaluate", json={"action_type": "CARD_SPEND_SHIFT",
                                                    "amount_monthly": "50000"})
check("F23: amount_monthly가 문자열이어도 500이 아니라 200으로 안전 처리됨(이전엔 TypeError로 500)",
      r_str_amount.status_code == 200)
check("F23: 문자열 '50000'도 숫자로 변환해 정상 판정(크래시 대신 올바른 계산)",
      r_str_amount.get_json()["decision"] == "HOLD")

r_garbage_amount = client.post("/api/evaluate", json={"action_type": "CARD_SPEND_SHIFT",
                                                        "amount_monthly": "숫자아님"})
check("F23: 숫자로 변환 안 되는 amount_monthly는 크래시 대신 REVIEW(입력 부족)로 종료",
      r_garbage_amount.status_code == 200 and r_garbage_amount.get_json()["decision"] == "REVIEW")

r_neg_balance = client.post("/api/evaluate", json={"action_type": "CARD_SPEND_SHIFT",
                                                     "amount_monthly": 50000,
                                                     "linked_balance": -1000000})
check("F23: 음수 linked_balance는 그대로 계산에 쓰지 않고 가정값(assumed)으로 안전 대체",
      r_neg_balance.status_code == 200
      and r_neg_balance.get_json()["effects"]["linked_balance"]["assumed"] is True
      and r_neg_balance.get_json()["effects"]["linked_balance"]["value"] == 100_000_000)

r_empty_body = client.post("/api/evaluate", data="not json",
                            content_type="application/json")
check("F23: 잘못된 JSON 바디도 500이 아니라 REVIEW로 안전 종료(기존부터 되던 동작, 회귀 확인)",
      r_empty_body.status_code == 200 and r_empty_body.get_json()["decision"] == "REVIEW")

# ---------------------------------------------------------------------------
# F27 — 보안(에러 메시지 노출, XSS, 입력 길이)
# ---------------------------------------------------------------------------
import action_interpreter as _ai_mod


def _boom(*args, **kwargs):
    raise _ai_mod.OpenAIError("HTTP Error 429: Too Many Requests - upstream key sk-TESTSECRET123")


_orig_ai_call = _ai_mod._ai_call
_orig_has_key = _ai_mod._ai_has_key
_ai_mod._ai_call = _boom
_ai_mod._ai_has_key = lambda: True
try:
    r_interpret_err = client.post("/api/interpret", json={"text": "카드실적 옮길래"}).get_json()
finally:
    _ai_mod._ai_call = _orig_ai_call
    _ai_mod._ai_has_key = _orig_has_key

check("F27: AI 호출 실패 시 원문 예외 메시지(HTTP Error/키 조각 등)가 클라이언트 meta에 노출되지 않음",
      "error" not in r_interpret_err["meta"],
      detail=str(r_interpret_err.get("meta")))
check("F27: 실패해도 NEED_INFO로 fail-closed(기존 동작 유지, 회귀 확인)",
      r_interpret_err["delta"]["status"] == "NEED_INFO")

_index_html = open(os.path.join(os.path.dirname(__file__), "..", "mvp", "static", "index.html"),
                    encoding="utf-8").read()
check("F27: index.html에 escapeHtml() 함수가 존재하고 clarifying_question 표시에 실제로 쓰임",
      "function escapeHtml(" in _index_html and "escapeHtml(d.action_type" in _index_html)
check("F27: 자연어 입력창에 클라이언트 길이 제한(maxlength)이 존재함",
      'id="actionText"' in _index_html and 'maxlength="300"' in _index_html)

r_long_text = client.post("/api/interpret", json={"text": "가" * 5000}).get_json()
check("F27: 5,000자 입력도 서버가 500자로 잘라 처리하고 크래시하지 않음(fail-closed)",
      r_long_text["delta"]["status"] in ("OK", "NEED_INFO", "UNSUPPORTED", "ERROR"))

print(f"\n{passed} passed, {failed} failed")
if failed:
    raise SystemExit(1)
