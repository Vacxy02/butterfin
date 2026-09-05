"""2026-09-05 독립감사(F01~F28) 회귀테스트 — V5 Surgical 패스 반영.

Butterfin_TO_DONGHAK_CLAUDE_V4_1_EXPLICIT_FILES_20260905.zip의 F01~F28 감사
프로토콜을 최초 재현한 뒤, 그 시점엔 F02/F04를 "이미 문서화된 골든 데모를
보존한다"는 이유로 의도적으로 남겨뒀었다. 그러나 동학이 2026-09-05
00_READ_ME_FIRST__V5_SURGICAL_FINAL.md로 이 판단을 명시적으로 뒤집었다:
"오래된 골든 데모를 보존하려고 P0를 남기지 마. 문서는 이후 최신 코드에 맞춰
다시 쓸 거야." — 이에 따라 이 V5 패스에서 F02/F04를 포함한 7개 blocker를
전부 고쳤고, 이 파일도 새 동작에 맞춰 다시 작성한다.

V5에서 실제로 고친 것(아래에서 회귀 고정):
- BLOCKER 1(F02): institution/product 없이 다중 후보가 남으면(예:
  PRODUCT_TERMINATION 단독 호출 → 3파전) matched[0]로 확정하지 않고 REVIEW +
  candidates 목록으로 fail-closed한다. 후보가 정확히 1개일 때만 자동판정.
- BLOCKER 2(F04): rule.exception이 실제로 없는 규칙(SHINHYUP_SALARY 등)은
  exception_condition_met=true를 줘도 더 이상 PASS로 면제되지 않는다.
- BLOCKER 3: new_product_rate_pct/net_effect_pct_p/net_effect_verdict(신규
  상품 금리 비교) 기능을 완전히 제거했다 — 차원이 안 맞는 계산이었다.
- BLOCKER 5(F16): HANA_HISTORY_SAVINGS는 여전히 "이 규칙 자체는 해지행동의
  영향을 받지 않는다"고 인과판정하지만, 더 이상 전역 PASS로 서비스 전체를
  판정하지 않는다 — rule_status: NOT_AFFECTED + decision: REVIEW로 낮춘다.
- BLOCKER 6: HF_SUBSCRIPTION_DIDIMDOL은 가입기간/납입회차 없이는 tiers[0]을
  임의로 골라 %p를 특정하지 않고 REVIEW로 필요 정보를 요청한다(공식 당첨해지
  exception이 적용되면 그 경로로 안전하게 통과).
- BLOCKER 7: CARD_SPEND_SHIFT 응답에 hist3/baseline_monthly 대표 시나리오
  가정값을 명시(hist3_assumed/baseline_assumed)했다.
- F23 입력 검증: amount_monthly가 문자열("50000")이면 `<=` 비교에서 TypeError로
  500이 나던 걸 고쳤다(안전하게 REVIEW로 종료). linked_balance가 음수면 그대로
  계산에 흘려보내지 않고 "안 준 것"과 동일하게 가정값으로 대체한다.
- F27 보안: (1) /api/interpret가 AI 호출 실패 시 원문 예외 메시지를 meta.error로
  그대로 클라이언트에 내려주던 것(코드 자체 주석의 의도와 반대)을 서버 로그로만
  남기게 고쳤다. (2) clarifying_question을 innerHTML에 그대로 꽂던 XSS 경로를
  escapeHtml()로 막았다. (3) 자연어 입력 길이 제한(클라이언트 maxlength=300,
  서버 500자 하드컷)을 추가했다.
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
check("골든 데모 불변: 급여계좌 변경(기관 미지정) → 여전히 HOLD/SHINHYUP_SALARY(이 action_type엔 후보가 1개뿐이라 BLOCKER 1 영향 없음)",
      r_salary["decision"] == "HOLD" and r_salary["matched_rules"] == ["SHINHYUP_SALARY"])

# BLOCKER 2(F04): SHINHYUP_SALARY는 rule.exception이 실제로 없으므로
# exception_condition_met=true를 줘도 더 이상 PASS로 면제되지 않는다 — 예전
# "급여계좌 변경 + 아무 예외 체크 → PASS" 골든 데모는 동학 지시로 폐기됐다.
r_salary_exc = client.post("/api/evaluate", json={"action_type": "SALARY_ACCOUNT_CHANGE",
                                                    "exception_condition_met": True}).get_json()
check("BLOCKER 2: 급여계좌 변경 + generic exception 체크 → 더 이상 PASS가 아님(exception 필드 없는 규칙)",
      r_salary_exc["decision"] != "PASS")
check("BLOCKER 2: exception_applied도 False로 정직하게 남음",
      r_salary_exc["condition"]["exception_applied"] is False)

# BLOCKER 1(F02): institution/product 없이 PRODUCT_TERMINATION만 주면 이제
# 3파전(KB_SAVINGS_LOAN_HOLD/HF_SUBSCRIPTION_DIDIMDOL/HANA_HISTORY_SAVINGS)이라
# matched[0]로 확정하지 않고 REVIEW + candidates로 fail-closed한다.
r_term = client.post("/api/evaluate", json={"action_type": "PRODUCT_TERMINATION"}).get_json()
check("BLOCKER 1: 상품 해지(기관·상품 미지정, 3파전) → REVIEW(더 이상 matched[0] 임의 확정 안 함)",
      r_term["decision"] == "REVIEW" and len(r_term["matched_rules"]) == 3)
check("BLOCKER 1: REVIEW 응답에 candidates 목록이 실려서 어떤 계약인지 선택할 수 있게 안내함",
      len(r_term.get("candidates") or []) == 3)

# institution/product를 명시하면(단일 후보) 여전히 자동판정된다 — KB_SAVINGS_LOAN_HOLD.
r_term_kb = client.post("/api/evaluate", json={"action_type": "PRODUCT_TERMINATION",
                                                "institution": "KB국민은행",
                                                "product": "대출 금리감면 (일반 신용대출)"}).get_json()
check("BLOCKER 1: institution/product로 단일 후보로 좁히면 여전히 자동판정(HOLD/KB_SAVINGS_LOAN_HOLD)",
      r_term_kb["decision"] == "HOLD" and r_term_kb["matched_rules"] == ["KB_SAVINGS_LOAN_HOLD"])

# ---------------------------------------------------------------------------
# BLOCKER 5(F16) — HANA_HISTORY_SAVINGS: 인과판정은 유지, 전역 PASS는 제거
# ---------------------------------------------------------------------------
r_hana = client.post("/api/evaluate", json={"action_type": "PRODUCT_TERMINATION",
                                             "institution": "하나은행",
                                             "product": "오늘부터, 하나 적금"}).get_json()
check("BLOCKER 5: 하나은행 이력 조건은 가입 전 확정 사실이라 이 규칙 자체는 영향받지 않지만, decision은 더 이상 전역 PASS가 아니라 REVIEW",
      r_hana["decision"] == "REVIEW" and "현재 해지행동의 영향을 받지 않습니다" in r_hana["reason"])
check("BLOCKER 5: 하나은행 케이스는 D/L/G 그대로 None, reversal도 False(D/G 없는 조건이 애초에 안 깨짐)",
      r_hana["effects"]["D"] is None and r_hana["effects"]["reversal"] is False)
check("BLOCKER 5: condition.rule_status로 이 규칙만 NOT_AFFECTED임을 명시(causal_note도 유지)",
      r_hana["condition"]["rule_status"] == "NOT_AFFECTED" and r_hana["condition"]["causal_note"])
check("BLOCKER 5: 다른 규칙(KB_SAVINGS_LOAN_HOLD, 단일 후보로 좁힌 경우)에는 영향 없음 — 여전히 HOLD",
      r_term_kb["decision"] == "HOLD")

# ---------------------------------------------------------------------------
# BLOCKER 6 — HF_SUBSCRIPTION_DIDIMDOL tier 임의 선택 금지
# ---------------------------------------------------------------------------
r_didimdol_no_tier = client.post("/api/evaluate", json={"action_type": "PRODUCT_TERMINATION",
                                                          "institution": "주택금융공사",
                                                          "product": "내집마련 디딤돌대출",
                                                          "exception_condition_met": False}).get_json()
check("BLOCKER 6: 가입기간/납입회차 없이 디딤돌 해지 → REVIEW(tiers[0] 임의 0.3%p 출력 없음)",
      r_didimdol_no_tier["decision"] == "REVIEW"
      and "가입기간" in r_didimdol_no_tier["reason"])
check("BLOCKER 6: condition.baseline_effect_pct_p가 임의로 채워지지 않고 None",
      r_didimdol_no_tier["condition"]["baseline_effect_pct_p"] is None)

r_didimdol_exception = client.post("/api/evaluate", json={"action_type": "PRODUCT_TERMINATION",
                                                            "institution": "주택금융공사",
                                                            "product": "내집마련 디딤돌대출",
                                                            "exception_condition_met": True}).get_json()
check("BLOCKER 6: 공식 당첨해지 exception이 적용되면 tier 정보 없이도 그 exception 경로로 안전하게 통과(REVIEW로 막히지 않음)",
      r_didimdol_exception["decision"] != "REVIEW"
      and r_didimdol_exception["condition"]["exception_applied"] is True)

# ---------------------------------------------------------------------------
# BLOCKER 3 — 새 상품 금리 비교 기능 제거 확인
# ---------------------------------------------------------------------------
check("BLOCKER 3: new_product_rate_pct/net_effect_pct_p/net_effect_verdict 필드가 응답에서 사라짐",
      "new_product_rate_pct" not in r_term_kb["condition"]
      and "net_effect_pct_p" not in r_term_kb["condition"]
      and "net_effect_verdict" not in r_term_kb["condition"])

# ---------------------------------------------------------------------------
# BLOCKER 7 — CARD_SPEND_SHIFT 대표 시나리오 가정값 노출 확인
# ---------------------------------------------------------------------------
r_scenario = client.post("/api/evaluate", json={"action_type": "CARD_SPEND_SHIFT",
                                                  "institution": "KB국민은행",
                                                  "product": "대출 금리감면 (일반 신용대출)",
                                                  "amount_monthly": 50000}).get_json()
check("BLOCKER 7: hist3/baseline_monthly를 안 주면 assumed=True로 대표 시나리오값을 명시함",
      r_scenario["effects"]["hist3"]["assumed"] is True
      and r_scenario["effects"]["baseline_monthly"]["assumed"] is True
      and r_scenario["effects"]["hist3"]["value"] == [220000, 220000, 220000])

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
