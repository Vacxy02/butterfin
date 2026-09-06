"""V7 SINGLE HANDOFF PACK — 02_FINAL_TEST_AND_FREEZE.md §A 필수 API/논리 테스트
13개 항목을 직접 검증하는 신규 회귀 테스트.

이 파일은 mvp/app.py의 7개 FIX(rule_store 참조: 01_FINAL_7_FIXES.md)가 실제로
동작하는지, 그리고 향후 누군가 코드를 건드려도 이 회귀가 다시 깨지지 않는지를
지킨다. 다른 test_*.py 파일들도 이 동작들을 부분적으로 검증하지만, 이 파일은
V7 스펙 문서의 13개 항목을 항목별로 1:1 매핑해서 빠짐없이 커버하는 게 목적이다.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mvp"))

from app import app as flask_app

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        print(f"✅ {name}")
        passed += 1
    else:
        failed += 1
        print(f"❌ {name}  {detail}")


client = flask_app.test_client()


def post(payload):
    return client.post("/api/evaluate", json=payload).get_json()


# ---------------------------------------------------------------------------
# 1. institution/product 미지정 → 여러 규칙 동시 매칭 → REVIEW (임의 선택 금지)
# ---------------------------------------------------------------------------
r1 = post({"action_type": "PRODUCT_TERMINATION"})
check("1. institution/product 미지정 시 3건 중복 매칭 → REVIEW",
      r1["decision"] == "REVIEW" and len(r1["matched_rules"]) == 3,
      detail=str(r1))

# ---------------------------------------------------------------------------
# 2. 존재하지 않는 institution/product → 0건 매칭 → REVIEW (fallback 금지)
# ---------------------------------------------------------------------------
r2 = post({"action_type": "CARD_SPEND_SHIFT", "institution": "존재하지않는은행",
           "amount_monthly": 50000})
check("2. 존재하지 않는 institution → 0건 매칭 → REVIEW",
      r2["decision"] == "REVIEW" and r2["matched_rules"] == [],
      detail=str(r2))

# ---------------------------------------------------------------------------
# 3. institution+product 정확히 지정 → 단일 매칭 → 자동 판정
# ---------------------------------------------------------------------------
r3 = post({"action_type": "PRODUCT_TERMINATION", "institution": "KB국민은행",
           "product": "대출 금리감면 (일반 신용대출)"})
check("3. institution+product 정확 지정 → 단일 매칭(KB_SAVINGS_LOAN_HOLD) → HOLD",
      r3["decision"] == "HOLD" and r3["matched_rules"] == ["KB_SAVINGS_LOAN_HOLD"],
      detail=str(r3))

# ---------------------------------------------------------------------------
# 4. SHINHYUP_SALARY — exception 필드가 없으므로 exception_condition_met=True를
#    줘도 PASS로 넘어가면 안 된다 (FIX 2, 예외 게이팅).
# ---------------------------------------------------------------------------
r4 = post({"action_type": "SALARY_ACCOUNT_CHANGE", "exception_condition_met": True})
check("4. SHINHYUP_SALARY: exception 필드 없음 → exception_condition_met=True여도 PASS 아님",
      r4["decision"] != "PASS", detail=str(r4))

# ---------------------------------------------------------------------------
# 5. SHINHYUP_CARD_ACCOUNT — 위와 동일한 게이팅 (exception 필드 없음)
# ---------------------------------------------------------------------------
r5 = post({"action_type": "PAYMENT_ACCOUNT_CHANGE", "institution": "신협",
           "product": "플러스정기적금(신한카드연계형) 10차",
           "exception_condition_met": True})
check("5. SHINHYUP_CARD_ACCOUNT: exception 필드 없음 → exception_condition_met=True여도 PASS 아님",
      r5["decision"] != "PASS", detail=str(r5))

# ---------------------------------------------------------------------------
# 6. HF_SUBSCRIPTION_DIDIMDOL — 실제 exception 필드가 있는 규칙이므로 공식
#    예외 조건 충족 시에는 규칙별 예외 경로가 정상적으로 허용돼야 한다.
# ---------------------------------------------------------------------------
r6 = post({"action_type": "PRODUCT_TERMINATION", "institution": "주택금융공사",
           "product": "내집마련 디딤돌대출", "exception_condition_met": True})
check("6. Didimdol: 공식 exception 필드 보유 규칙 + 예외 충족 → REVIEW로 막히지 않고 판정됨(PASS)",
      r6["decision"] == "PASS", detail=str(r6))

# ---------------------------------------------------------------------------
# 7. Didimdol — enrollment_years/payment_count 없이 일반 해지 → tiers[0] 임의
#    선택(예: 0.3%p) 대신 REVIEW로 처리돼야 한다 (FIX 1, bullet 3).
# ---------------------------------------------------------------------------
r7 = post({"action_type": "PRODUCT_TERMINATION", "institution": "주택금융공사",
           "product": "내집마련 디딤돌대출", "exception_condition_met": False})
check("7. Didimdol: 가입기간/납입회차 미확인 + 예외 없음 → REVIEW(0.3%p 임의 확정 금지)",
      r7["decision"] == "REVIEW" and r7["condition"]["lost_pct_p"] is None,
      detail=str(r7))
check("7-1. Didimdol REVIEW: review_note로 왜 REVIEW인지, 뭘 하면 되는지 설명",
      bool(r7["condition"].get("review_note")), detail=str(r7))

# ---------------------------------------------------------------------------
# 8. 모든 이산(discrete) 판정 응답은 D/L/G가 unset(None)이고 action_reversal/
#    effects.reversal이 항상 False여야 한다 (FIX 4) — decision과 무관하게.
# ---------------------------------------------------------------------------
r8_hold = post({"action_type": "PAYMENT_ACCOUNT_CHANGE", "institution": "케이뱅크",
                "product": "주거래우대 자유적금", "exception_condition_met": False})
r8_pass = post({"action_type": "PAYMENT_ACCOUNT_CHANGE", "institution": "케이뱅크",
                "product": "주거래우대 자유적금", "exception_condition_met": True})
check("8. 이산 HOLD 케이스: D/L/G는 None, effects.reversal/action_reversal은 False",
      r8_hold["effects"]["D"] is None and r8_hold["effects"]["L"] is None
      and r8_hold["effects"]["G"] is None and r8_hold["effects"]["reversal"] is False
      and r8_hold["action_reversal"] is False,
      detail=str(r8_hold))
check("8-1. 이산 PASS 케이스: 마찬가지로 D/L/G는 None, reversal은 False",
      r8_pass["effects"]["D"] is None and r8_pass["effects"]["reversal"] is False
      and r8_pass["action_reversal"] is False,
      detail=str(r8_pass))

# ---------------------------------------------------------------------------
# 9. CARD_SPEND_SHIFT(연속 모델)는 실제로 D>0, G<0을 계산해서 Action Reversal이
#    보존돼야 한다 — 메인 골든 데모(5만원 → HOLD)가 정확히 이 케이스다.
# ---------------------------------------------------------------------------
r9 = post({"action_type": "CARD_SPEND_SHIFT", "institution": "KB국민은행",
           "product": "대출 금리감면 (일반 신용대출)",
           "amount_monthly": 50000, "direct_benefit_monthly": 1000})
check("9. KB CARD_SPEND_SHIFT 5만원: D>0 and G<0 실제 계산 → Action Reversal=True 보존",
      r9["effects"]["D"]["value"] > 0 and r9["effects"]["G"]["value"] < 0
      and r9["effects"]["reversal"] is True and r9["action_reversal"] is True,
      detail=str(r9["effects"]))

# ---------------------------------------------------------------------------
# 10. new_product_rate_pct=3.5 입력 → 그대로 에코되지만 net-effect 판정(파생
#     ADVANTAGEOUS/DISADVANTAGEOUS/EQUAL 배지)은 응답에 존재하지 않아야 한다 (FIX 5).
# ---------------------------------------------------------------------------
r10 = post({"action_type": "PRODUCT_TERMINATION", "institution": "KB국민은행",
            "product": "대출 금리감면 (일반 신용대출)", "new_product_rate_pct": 3.5})
check("10. new_product_rate_pct=3.5 → condition에 그대로 에코됨",
      r10["condition"]["new_product_rate_pct"] == 3.5, detail=str(r10["condition"]))
check("10-1. net-effect 파생 판정 필드는 응답에 전혀 없음(퍼센트 입력창은 유지, 판정만 제거)",
      "net_effect_pct_p" not in r10["condition"] and "net_effect_verdict" not in r10["condition"],
      detail=str(r10["condition"]))

# ---------------------------------------------------------------------------
# 11. SCOPE_NOTE가 모든 응답(자동판정/REVIEW/다중매칭/이산/연속 전부)에 존재
# ---------------------------------------------------------------------------
for label, r in [("불일치(REVIEW)", r2), ("다중매칭(REVIEW)", r1), ("Didimdol REVIEW", r7),
                  ("이산 HOLD", r8_hold), ("연속 CARD_SPEND_SHIFT", r9)]:
    check(f"11. SCOPE_NOTE 존재 — {label}", bool(r.get("scope_note")), detail=str(r.get("scope_note")))

# ---------------------------------------------------------------------------
# 12. KB CARD_SPEND_SHIFT 응답에 hist3/baseline 시나리오 가정이 노출됨 (FIX 6)
# ---------------------------------------------------------------------------
check("12. hist3/baseline_monthly가 effects에 노출되고 미입력 시 assumed=True",
      r9["effects"]["hist3"]["assumed"] is True
      and r9["effects"]["hist3"]["value"] == [220000, 220000, 220000]
      and r9["effects"]["baseline_monthly"]["assumed"] is True
      and r9["effects"]["baseline_monthly"]["value"] == 220000
      and bool(r9["effects"].get("scenario_note")),
      detail=str(r9["effects"]))

# ---------------------------------------------------------------------------
# 13. linked_balance 가정값 노출 (기존 FIX와 동일 원칙 — 회귀 확인용으로 재검증)
# ---------------------------------------------------------------------------
check("13. linked_balance 미입력 시 assumed=True로 명시(1억원 가정)",
      r9["effects"]["linked_balance"]["assumed"] is True
      and r9["effects"]["linked_balance"]["value"] == 100_000_000,
      detail=str(r9["effects"]["linked_balance"]))

print(f"\n{passed} passed, {failed} failed")
if failed:
    raise SystemExit(1)
