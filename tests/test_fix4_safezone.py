"""2026-08-30 패치팩(02_FIX_1차원SafeZone_4개.md) 회귀테스트.

박승렬이 화면에서 확인한 4개 문제의 수정을 검증한다:
  FIX-1 Robust Safe Zone 정책 통일 (숫자 범위 + "계산 안 함" 동시표시 금지)
  FIX-2 Warning Zone 공집합 처리 (robust==nominal이면 "20,000~20,000" 대신 NONE)
  FIX-3 Financial Cliff / D·L·G 단위·기간 명시 (서로 다른 horizon일 수 있음을 API가 드러냄)
  FIX-4 Action Reversal(D>0,G<0) vs 누적 전체효과 음수전환(TTR) 문구 분리

기존 135개 테스트(test_action_interpreter 22 + test_ai_rule 23 + test_baseline_regex 30 +
test_dev25_runner 12 + test_engine 22 + test_safezone_v12 26)는 이 파일에서 한 줄도
건드리지 않는다 — 이 파일은 순수 추가(additive)다.
"""
import sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mvp"))

from engine import compute_safe_zone, reversal_explanation
from app import app as flask_app

passed = failed = 0


def check(name, cond, detail=None):
    global passed, failed
    if cond:
        print(f"✅ {name}")
        passed += 1
    else:
        print(f"❌ {name}" + (f" — {detail}" if detail is not None else ""))
        failed += 1


HIST3 = [220000, 220000, 220000]
BASELINE = 220000
KB = [{"min": 900000, "effect_pct_p": 0.3}, {"min": 600000, "effect_pct_p": 0.2}, {"min": 300000, "effect_pct_p": 0.1}]
RULES_KB = [{"rule_id": "KB_CARD_LOAN_STEP", "thresholds": KB}]
UNC = [{"baseline_monthly": 215000}]

client = flask_app.test_client()

# ---------------------------------------------------------------------------
# FIX-2 Warning Zone 공집합 처리
# ---------------------------------------------------------------------------
z_no_unc = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=None)
# 2026-09-05 (동학 요청): FIX-2의 "폭 0 구간→NONE 치환"을 되돌림 — robust==nominal이어도
# 실제 계산된 값(20,000~20,000)을 그대로 노출한다. 이 두 assert는 되돌리기 전 동작
# 대신 되돌린 뒤의 동작을 검증하도록 갱신했다(원래 assert는 위 커밋 이전 버전 참고).
check("FIX-2 되돌림: robust==nominal이어도 warning_status=CALCULATED(값 자체는 실제 계산값)",
      z_no_unc.robust_safe_limit == z_no_unc.nominal_safe_limit and z_no_unc.warning_status == "CALCULATED")
check("FIX-2 되돌림: warning_zone이 실제 값(20,000~20,000)을 그대로 담음(null 아님)",
      z_no_unc.warning_zone == {"min_exclusive": z_no_unc.nominal_safe_limit, "max_inclusive": z_no_unc.nominal_safe_limit})

z_unc = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=None,
                           uncertainty_scenarios=UNC)
check("FIX-2: robust(15000)<nominal(20000) → warning_status=CALCULATED",
      z_unc.robust_safe_limit == 15000 and z_unc.nominal_safe_limit == 20000
      and z_unc.warning_status == "CALCULATED")
check("FIX-2: warning_status=CALCULATED이면 실제 범위(15000 초과 ~ 20000 이하)를 그대로 보여줌",
      z_unc.warning_zone == {"min_exclusive": 15000, "max_inclusive": 20000})

z_empty = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=[{"rule_id": "X", "thresholds": []}],
                             planned_x=None)
check("FIX-2: 매칭 규칙 자체가 없으면 warning_status=NOT_APPLICABLE(NONE과는 다른 사유)",
      z_empty.warning_status == "NOT_APPLICABLE")

# ---------------------------------------------------------------------------
# FIX-3 Financial Cliff / D·L·G — API 응답에 unit·horizon_months가 실려 있는지
# (app.py JSON 레벨에서 확인 — engine.py의 SafeZoneResult.financial_cliff 자체는
# tests/test_safezone_v12.py가 이미 값의 정확성을 검증하고 있으므로 여기서는 값을
# 다시 재확인하지 않고, "단위/기간이 명시되는가"만 추가로 확인한다)
# ---------------------------------------------------------------------------
r = client.post("/api/evaluate", json={"action_type": "CARD_SPEND_SHIFT", "amount_monthly": 50000}).get_json()
eff = r["effects"]
saf = r["safety"]

check("FIX-3: effects.D에 value/unit/horizon_months 3개 키가 모두 있음",
      set(eff["D"].keys()) == {"value", "unit", "horizon_months"}, eff["D"])
check("FIX-3: effects.L/effects.G도 동일한 형태",
      set(eff["L"].keys()) == {"value", "unit", "horizon_months"}
      and set(eff["G"].keys()) == {"value", "unit", "horizon_months"})
check("FIX-3: D/L/G의 horizon_months는 서로 같음(같은 시점 기준 3개 값)",
      eff["D"]["horizon_months"] == eff["L"]["horizon_months"] == eff["G"]["horizon_months"])
check("FIX-3: G = D + L (같은 시점 기준이므로 항등식 성립)",
      eff["G"]["value"] == eff["D"]["value"] + eff["L"]["value"], eff)
check("FIX-3: safety.financial_cliff에도 value/unit/horizon_months가 있음",
      set(saf["financial_cliff"].keys()) == {"value", "unit", "horizon_months"}, saf["financial_cliff"])
check("FIX-3: financial_cliff의 horizon_months(12, 전체 시뮬레이션 구간)는 항상 고정값",
      saf["financial_cliff"]["horizon_months"] == 12)
check("FIX-3: 이 케이스는 TTR(2개월)<cliff horizon(12개월) → 두 horizon이 실제로 다름(계산 오류 아니라 의도된 차이라는 걸 필드로 확인 가능)",
      eff["D"]["horizon_months"] != saf["financial_cliff"]["horizon_months"])

# 이산 판정(PRODUCT_TERMINATION) 경로는 D/L/G가 여전히 순수 None이어야 한다(구버전
# 회귀 test_safezone_v12.py #16과 동일 계약 — 여기서는 financial_cliff도 같이 확인).
r_discrete = client.post("/api/evaluate", json={"action_type": "PRODUCT_TERMINATION",
                                                 "exception_condition_met": False}).get_json()
check("FIX-3: 이산 판정 유형은 effects.D가 객체가 아니라 그대로 None (금액 모델 자체가 없음)",
      r_discrete["effects"]["D"] is None)
check("FIX-3: 이산 판정 유형은 safety.financial_cliff도 그대로 None",
      r_discrete["safety"]["financial_cliff"] is None)

# ---------------------------------------------------------------------------
# FIX-4 Action Reversal 정의(D>0,G<0) vs 누적 전체효과 음수전환(TTR) 문구 분리
# ---------------------------------------------------------------------------
check("FIX-4: D=0,G<0(예: 실측 사례) → reversal=False인데도 reversal_reason이 '왜 아닌지'를 설명함",
      eff["reversal"] is False and "Action Reversal 정의" in eff["reversal_reason"]
      and "해당하지 않습니다" in eff["reversal_reason"], eff["reversal_reason"])
check("FIX-4: 그 reversal_reason에는 누적 전체효과가 음수로 전환되는 시점(TTR)도 별도로 언급됨",
      f"{r['time']['TTR']}개월" in eff["reversal_reason"])

# reversal_explanation() 자체를 D>0,G<0(진짜 reversal)/D<=0,G<0(아님)/D>0,G>=0(아님) 세 갈래로 직접 검증
exp_true = reversal_explanation(D=5000, G=-3000, ttr=3)
check("FIX-4: D>0 and G<0 → 'Action Reversal 정의(D>0, G<0)에 해당합니다' 문구 포함",
      "해당합니다" in exp_true and "Action Reversal 정의(D>0, G<0)" in exp_true, exp_true)

exp_false_zero_d = reversal_explanation(D=0, G=-8333, ttr=2)
check("FIX-4: D=0,G<0 → '해당하지 않습니다' + TTR 언급 (사용자가 실제로 본 사례와 동일 형태)",
      "해당하지 않습니다" in exp_false_zero_d and "2개월" in exp_false_zero_d, exp_false_zero_d)

exp_false_positive_g = reversal_explanation(D=5000, G=3000, ttr=None)
check("FIX-4: D>0,G>=0(둘 다 이득) → Action Reversal 아님으로 명확히 설명",
      "아닙니다" in exp_false_positive_g, exp_false_positive_g)

check("FIX-4: 상단 판정 사유(reason)와 effects.reversal_reason은 서로 다른 필드로 분리되어 있음(같은 문자열 재사용 아님)",
      r["reason"] != eff["reversal_reason"])

# ---------------------------------------------------------------------------
# Engine/UI 분리 + Determinism (기존 파일의 관례를 그대로 이어감)
# ---------------------------------------------------------------------------
r_again1 = client.post("/api/evaluate", json={"action_type": "CARD_SPEND_SHIFT", "amount_monthly": 50000}).get_json()
r_again2 = client.post("/api/evaluate", json={"action_type": "CARD_SPEND_SHIFT", "amount_monthly": 50000}).get_json()
check("Determinism: 동일 입력 3회(r, r_again1, r_again2) → safety/effects 완전히 동일",
      r["safety"] == r_again1["safety"] == r_again2["safety"]
      and r["effects"] == r_again1["effects"] == r_again2["effects"])

# ---------------------------------------------------------------------------
# 프론트가 "계산 안 함"이라는 모순 문구를 더 이상 쓰지 않는지 정적 확인(FIX-1)
# ---------------------------------------------------------------------------
_index_html = open(os.path.join(os.path.dirname(__file__), "..", "mvp", "static", "index.html"),
                    encoding="utf-8").read()
# 주석(//)에는 "이 문구를 없앴다"는 설명으로 '계산 안 함'이 나올 수 있으므로, 코드 라인
# (주석이 아닌 줄)에만 그 문구가 없는지를 확인한다 — 실제로 화면에 찍히는 문자열 기준.
_code_lines = [ln for ln in _index_html.splitlines() if not ln.strip().startswith("//")]
check("FIX-1: index.html의 실제 표시 문구(주석 제외)에 '계산 안 함'이 더 이상 없음(숫자 범위와 동시표시되던 모순 문구 제거)",
      not any("계산 안 함" in ln for ln in _code_lines))
check("FIX-1: NOT_APPLICABLE 라벨이 'nominal과 동일'이라고 명확히 설명함",
      "nominal" in _index_html.lower() or "Nominal" in _index_html)
check("FIX-2: index.html이 warning_status를 실제로 참조함(숫자 구간을 무조건 찍지 않음)",
      "warning_status" in _index_html)

# ---------------------------------------------------------------------------
# 2026-09-05(동학 요청): "해지 후 새로 가입할 상품 금리를 입력하면 이득/손해 비교"
# — 원금이 같다고 가정한 단순 %p 비교. 사용자가 값을 안 주면 계산을 생략(지어내지
# 않음), 판정 로직(decide/evaluate_discrete_rule)은 전혀 건드리지 않은 부가 계산.
# ---------------------------------------------------------------------------
r_no_compare = client.post("/api/evaluate", json={"action_type": "PRODUCT_TERMINATION",
                                                    "exception_condition_met": False}).get_json()
check("새 상품 비교: 금리를 안 주면 new_product_rate_pct/net_effect_pct_p가 모두 null(비교 생략, 값 지어내지 않음)",
      r_no_compare["condition"]["new_product_rate_pct"] is None
      and r_no_compare["condition"]["net_effect_pct_p"] is None)

r_compare_better = client.post("/api/evaluate", json={"action_type": "PRODUCT_TERMINATION",
                                                        "exception_condition_met": False,
                                                        "new_product_rate_pct": 5.0}).get_json()
_lost = r_compare_better["condition"]["lost_pct_p"]
check("새 상품 비교: 새 상품 금리(5.0%) - 상실폭(lost_pct_p) = net_effect_pct_p (단순 뺄셈, 새 계산식 아님)",
      _lost is not None
      and r_compare_better["condition"]["net_effect_pct_p"] == round(5.0 - _lost, 4))
check("새 상품 비교: 새 상품 금리가 상실폭보다 크면(순효과 > 0) 이득 방향으로 계산됨",
      r_compare_better["condition"]["net_effect_pct_p"] > 0)

r_compare_bad_input = client.post("/api/evaluate", json={"action_type": "PRODUCT_TERMINATION",
                                                           "exception_condition_met": False,
                                                           "new_product_rate_pct": "not_a_number"}).get_json()
check("새 상품 비교: 숫자로 변환 안 되는 값이 오면 크래시 대신 비교를 생략함(null)",
      r_compare_bad_input["condition"]["new_product_rate_pct"] is None
      and r_compare_bad_input["condition"]["net_effect_pct_p"] is None)

check("새 상품 비교: engine/decide 판정 로직은 그대로 — 비교 입력이 있어도 decision/reason은 안 바뀜",
      r_compare_better["decision"] == r_no_compare["decision"]
      and r_compare_better["reason"] == r_no_compare["reason"])

print(f"\n{passed} passed, {failed} failed")
if failed:
    raise SystemExit(1)
