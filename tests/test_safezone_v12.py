"""수학 v1.2 Safe Zone 확장 회귀테스트 — 04_신규_회귀테스트_명세.md의 25개 필수 케이스.

기존 95개 테스트(test_engine.py 22 + test_ai_rule.py 23 + test_baseline_regex.py 30 +
test_dev25_runner.py 12 + test_action_interpreter.py 8)는 이 파일에서 한 줄도 건드리지
않는다 — 이 파일은 순수 추가(additive)다.

engine.py의 compute_safe_zone()/simulate()와 app.py(/api/evaluate)의 실제 동작을 그대로
호출해서 검증한다 — 숫자는 전부 이 코드를 실제로 실행해서 얻은 값이다(재현 가능,
임의로 지어낸 "기대값"이 아니다).

각 테스트는 명세 §"테스트 증거"의 요구대로 input/expected/actual/pass-fail을 저장한다
(evidence 리스트 → 실행 시 tests/safezone_v12_evidence.json으로 저장).
"""
import sys, os, json, math
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mvp"))

from engine import simulate, compute_safe_zone

passed = failed = 0
evidence = []


def record(name, input_data, expected, actual, ok):
    global passed, failed
    evidence.append({
        "name": name, "input": input_data, "expected": expected, "actual": actual,
        "status": "PASS" if ok else "FAIL",
    })
    if ok:
        print(f"✅ {name}")
        passed += 1
    else:
        print(f"❌ {name} — expected {expected}, got {actual}")
        failed += 1


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol


# ---- 공통 픽스처 (test_engine.py의 KB_CARD_LOAN_STEP T1/2/3 실측치와 동일) ----
HIST3 = [220000, 220000, 220000]
BASELINE = 220000
KB = [
    {"min": 900000, "effect_pct_p": 0.3},
    {"min": 600000, "effect_pct_p": 0.2},
    {"min": 300000, "effect_pct_p": 0.1},
    {"min": 0, "effect_pct_p": 0.0},
]
RULES_KB = [{"rule_id": "KB", "thresholds": KB}]

# ============================================================================
# 1. 단일 계약 nominal Safe Limit 정상
# ============================================================================
z1 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=None)
record("1. 단일 계약 nominal Safe Limit 정상",
       {"hist3": HIST3, "baseline_monthly": BASELINE, "rules": ["KB"]},
       20000, z1.nominal_safe_limit, z1.nominal_safe_limit == 20000)

# ============================================================================
# uncertainty 시나리오 (2~6, 10에서 공용) — hist3/baseline이 실제로 "이럴 수도 있다"는
# 확인된 대안(베이스라인이 낮게 나올 수 있는 보수적 시나리오)을 준다. robust=15000 < nominal=20000.
# ============================================================================
UNC = [{"baseline_monthly": 215000}]

# 2. 계획 행동 < robust limit → SAFE
z2 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=10000, uncertainty_scenarios=UNC)
record("2. 계획 행동 < robust limit → SAFE",
       {"planned_x": 10000, "uncertainty_scenarios": UNC}, "SAFE", z2.current_zone, z2.current_zone == "SAFE")

# 3. 계획 행동 = robust limit → SAFE
z3 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=15000, uncertainty_scenarios=UNC)
record("3. 계획 행동 = robust limit → SAFE",
       {"planned_x": 15000, "robust_limit": z3.robust_safe_limit}, "SAFE", z3.current_zone,
       z3.robust_safe_limit == 15000 and z3.current_zone == "SAFE")

# 4. robust limit + 1 최소단위 → WARNING
z4 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=16000, uncertainty_scenarios=UNC)
record("4. robust limit + 1 최소단위(1,000원) → WARNING",
       {"planned_x": 16000, "robust_limit": 15000, "step": 1000}, "WARNING", z4.current_zone, z4.current_zone == "WARNING")

# 5. 계획 행동 = nominal limit → WARNING(불확실성 있음) / SAFE(robust=nominal이면)
z5_unc = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=20000, uncertainty_scenarios=UNC)
z5_no_unc = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=20000)
record("5a. 계획 행동 = nominal limit, robust<nominal → WARNING",
       {"planned_x": 20000, "nominal": 20000, "robust": 15000}, "WARNING", z5_unc.current_zone,
       z5_unc.current_zone == "WARNING")
record("5b. 계획 행동 = nominal limit, robust=nominal(불확실성 없음) → SAFE",
       {"planned_x": 20000, "nominal": 20000, "robust": z5_no_unc.robust_safe_limit}, "SAFE", z5_no_unc.current_zone,
       z5_no_unc.robust_safe_limit == 20000 and z5_no_unc.current_zone == "SAFE")

# 6. nominal limit + 1 최소단위 → BREACH
z6 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=21000, uncertainty_scenarios=UNC)
record("6. nominal limit + 1 최소단위(1,000원) → BREACH",
       {"planned_x": 21000, "nominal": 20000}, "BREACH", z6.current_zone, z6.current_zone == "BREACH")

# ============================================================================
# 7. 다중계약 서로 다른 limit → 최소값 선택
# ============================================================================
STRICT = [{"min": 650000, "effect_pct_p": 0.25}, {"min": 0, "effect_pct_p": 0.0}]
RULES_MULTI_DIFF = [{"rule_id": "KB", "thresholds": KB}, {"rule_id": "STRICT", "thresholds": STRICT}]
z7 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_MULTI_DIFF, planned_x=5000)
record("7. 다중계약 서로 다른 limit → 최소값(더 엄격한 계약) 선택",
       {"rules": ["KB(20000)", "STRICT(더 엄격)"]}, {"nominal": 3000, "binding": ["STRICT"]},
       {"nominal": z7.nominal_safe_limit, "binding": z7.binding_constraints},
       z7.nominal_safe_limit == 3000 and z7.binding_constraints == ["STRICT"])

# ============================================================================
# 8. 다중계약 binding 동률 → binding list 2개 이상
# ============================================================================
RULES_TIE = [{"rule_id": "KB1", "thresholds": KB}, {"rule_id": "KB2", "thresholds": KB}]
z8 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_TIE, planned_x=5000)
record("8. 다중계약 binding 동률 → binding_constraints 2개 이상, 하나로 임의 축약 안 함",
       {"rules": ["KB1(20000)", "KB2(20000, 동일)"]}, {"nominal": 20000, "binding_count": 2},
       {"nominal": z8.nominal_safe_limit, "binding": z8.binding_constraints},
       z8.nominal_safe_limit == 20000 and set(z8.binding_constraints) == {"KB1", "KB2"})

# ============================================================================
# 9. uncertainty 없음 → robust=nominal 또는 N/A 정책 일관성
# ============================================================================
z9 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=None)
record("9. uncertainty 없음 → robust_status=NOT_APPLICABLE, robust=nominal (임의 버퍼 미생성)",
       {"uncertainty_scenarios": None}, {"robust_status": "NOT_APPLICABLE", "robust": 20000},
       {"robust_status": z9.robust_status, "robust": z9.robust_safe_limit},
       z9.robust_status == "NOT_APPLICABLE" and z9.robust_safe_limit == z9.nominal_safe_limit == 20000)

# ============================================================================
# 10. uncertainty 존재 → robust < nominal
# ============================================================================
z10 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=None, uncertainty_scenarios=UNC)
record("10. 확인된 uncertainty 존재 → robust(15000) < nominal(20000), status=CALCULATED",
       {"uncertainty_scenarios": UNC}, {"robust": 15000, "status": "CALCULATED"},
       {"robust": z10.robust_safe_limit, "status": z10.robust_status},
       z10.robust_safe_limit == 15000 and z10.robust_safe_limit < z10.nominal_safe_limit and z10.robust_status == "CALCULATED")

# ============================================================================
# 11. uncertainty 너무 큼 → EMPTY_SAFE_ZONE
# ============================================================================
UNC_EXTREME = [{"baseline_monthly": 150000}]
z11 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=None, uncertainty_scenarios=UNC_EXTREME)
record("11. 최악 시나리오에서 robust<=0 → EMPTY_SAFE_ZONE (안전구간 없음을 숨기지 않음)",
       {"uncertainty_scenarios": UNC_EXTREME}, {"robust": 0, "status": "EMPTY_SAFE_ZONE"},
       {"robust": z11.robust_safe_limit, "status": z11.robust_status},
       z11.robust_safe_limit == 0 and z11.robust_status == "EMPTY_SAFE_ZONE")

# ============================================================================
# 12. 현재 상태가 이미 breach → safe limit 0/정책 확인
# ============================================================================
HIST3_BREACHED = [400000, 400000, 400000]
BASELINE_LOW = 100000
RULES_BREACH = [{"rule_id": "KB", "thresholds": KB}]
z12_at0 = compute_safe_zone(hist3=HIST3_BREACHED, baseline_monthly=BASELINE_LOW, rules=RULES_BREACH, planned_x=0)
z12_at1000 = compute_safe_zone(hist3=HIST3_BREACHED, baseline_monthly=BASELINE_LOW, rules=RULES_BREACH, planned_x=1000)
record("12. 이미 breach 상태(baseline 자체가 tier 유지 불가) → nominal_safe_limit=0, 경계 정책 일관성",
       {"hist3": HIST3_BREACHED, "baseline_monthly": BASELINE_LOW, "planned_x": [0, 1000]},
       {"nominal": 0, "zone@0": "SAFE(폭0 경계 포함)", "zone@1000": "BREACH"},
       {"nominal": z12_at0.nominal_safe_limit, "zone@0": z12_at0.current_zone, "zone@1000": z12_at1000.current_zone},
       z12_at0.nominal_safe_limit == 0 and z12_at0.current_zone == "SAFE" and z12_at1000.current_zone == "BREACH")

# ============================================================================
# 13. Financial Cliff 양수/음수 부호 일관성
# ============================================================================
z13 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=None,
                         linked_balance=100_000_000, direct_benefit_monthly=0)
# 독립적으로 직접 재계산해서 부호/값이 engine 내부 계산과 일치하는지 검증 (자체 일관성)
below = simulate(hist3=HIST3, baseline_monthly=BASELINE, shift_monthly=z13.nominal_safe_limit - 1000,
                  thresholds=KB, linked_balance=100_000_000, direct_benefit_monthly=0, horizon=12)
above = simulate(hist3=HIST3, baseline_monthly=BASELINE, shift_monthly=z13.nominal_safe_limit + 1000,
                  thresholds=KB, linked_balance=100_000_000, direct_benefit_monthly=0, horizon=12)
independent_cliff = above.G[-1] - below.G[-1]
record("13. Financial Cliff 부호 일관성 (breach 넘으면 우대 tier 하락 → G 점프는 음수, 독립 재계산과 일치)",
       {"nominal": z13.nominal_safe_limit, "linked_balance": 100_000_000},
       {"sign": "negative", "matches_independent_calc": True},
       {"financial_cliff": z13.financial_cliff, "independent_cliff": independent_cliff, "status": z13.cliff_status},
       z13.cliff_status == "CALCULATED" and z13.financial_cliff < 0 and close(z13.financial_cliff, independent_cliff))

# ============================================================================
# 14. 연속형 효과(실제 불연속 없음) → cliff N/A 또는 0
# ============================================================================
FLAT = [{"min": 0, "effect_pct_p": 0.1}]  # 전 구간 동일 우대 — tier가 절대 안 바뀜 → 진짜 불연속 없음
RULES_FLAT = [{"rule_id": "FLAT", "thresholds": FLAT}]
z14 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_FLAT, planned_x=None, linked_balance=100_000_000)
record("14. 실제 breach 경계가 없는(단일 평평한 tier) 계약 → cliff NOT_APPLICABLE (억지로 값 만들지 않음)",
       {"thresholds": "단일 평평한 tier(전 구간 0.1%p)"}, {"cliff": None, "status": "NOT_APPLICABLE"},
       {"cliff": z14.financial_cliff, "status": z14.cliff_status},
       z14.cliff_status == "NOT_APPLICABLE" and z14.financial_cliff is None)

# ============================================================================
# 15. D known / L known / G known
# ============================================================================
sim15 = simulate(hist3=HIST3, baseline_monthly=BASELINE, shift_monthly=30000, thresholds=KB,
                  linked_balance=100_000_000, direct_benefit_monthly=3000, horizon=12)
record("15. D/L/G 전부 known일 때 G=D+L 항등식 성립 (t=4)",
       {"shift_monthly": 30000, "direct_benefit_monthly": 3000, "t": 4},
       {"D": 12000.0, "L": -16666.6667, "G": -4666.6667},
       {"D": sim15.D[4], "L": round(sim15.L[4], 4), "G": round(sim15.G[4], 4)},
       close(sim15.D[4], 12000.0) and close(sim15.L[4], -16666.6667, 1e-3)
       and close(sim15.G[4], sim15.D[4] + sim15.L[4]))

# ============================================================================
# 16. D unknown(이산 판정 유형) → G/Reversal 과잉 계산 금지 — app.py 실제 응답으로 검증
# ============================================================================
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mvp"))
from app import app as flask_app
_client = flask_app.test_client()
r16_violate = _client.post('/api/evaluate', json={"action_type": "PRODUCT_TERMINATION", "exception_condition_met": False}).get_json()
r16_exempt = _client.post('/api/evaluate', json={"action_type": "PRODUCT_TERMINATION", "exception_condition_met": True}).get_json()
record("16. D unknown(이산 판정) → effects.D/L/G는 None으로 정직하게 남고, reversal은 D/G로 계산하지 않고 이산판정 그대로 사용",
       {"action_type": "PRODUCT_TERMINATION", "exception_condition_met": [False, True]},
       {"violation_case": {"D": None, "reversal": True}, "exempt_case": {"D": None, "reversal": False}},
       {"violation_case": r16_violate["effects"], "exempt_case": r16_exempt["effects"]},
       r16_violate["effects"]["D"] is None and r16_violate["effects"]["reversal"] is True
       and r16_exempt["effects"]["D"] is None and r16_exempt["effects"]["reversal"] is False)

# ============================================================================
# 17. Optimal Safe Range 존재
# ============================================================================
z17 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=None,
                         linked_balance=100_000_000, direct_benefit_monthly=0)
record("17. G 계산 근거(linked_balance) 있고 robust>0 → Optimal Safe Range 계산됨",
       {"linked_balance": 100_000_000, "robust": z17.robust_safe_limit},
       {"status": "CALCULATED", "range": {"min": 0, "max": 20000}},
       {"status": z17.optimal_status, "range": z17.optimal_safe_range},
       z17.optimal_status == "CALCULATED" and z17.optimal_safe_range == {"min": 0, "max": 20000})

# ============================================================================
# 18. G unknown(linked_balance 없음) → Optimal Safe Range 계산 금지
# ============================================================================
z18 = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_KB, planned_x=None)
record("18. G 계산 근거(linked_balance) 없음 → Optimal Safe Range 계산 안 함(UNKNOWN_EFFECT), None으로 지어내지 않음",
       {"linked_balance": None}, {"status": "UNKNOWN_EFFECT", "range": None},
       {"status": z18.optimal_status, "range": z18.optimal_safe_range},
       z18.optimal_status == "UNKNOWN_EFFECT" and z18.optimal_safe_range is None)

# ============================================================================
# 19. Optimal Safe Range가 robust zone 밖으로 나가지 않음
# ============================================================================
record("19. Optimal Safe Range ⊆ [0, robust_safe_limit] (robust zone을 벗어나지 않음)",
       {"robust": z17.robust_safe_limit, "optimal": z17.optimal_safe_range},
       {"min>=0": True, "max<=robust": True},
       {"min": z17.optimal_safe_range["min"], "max": z17.optimal_safe_range["max"], "robust": z17.robust_safe_limit},
       z17.optimal_safe_range["min"] >= 0 and z17.optimal_safe_range["max"] <= z17.robust_safe_limit)

# ============================================================================
# 20. TTB < TTR
# ============================================================================
sim20 = simulate(hist3=HIST3, baseline_monthly=BASELINE, shift_monthly=30000, thresholds=KB,
                  linked_balance=100_000_000, direct_benefit_monthly=3000, horizon=12)
record("20. TTB < TTR (tier는 3개월째 바뀌지만, 누적 손익은 4개월째에야 마이너스로 전환)",
       {"shift_monthly": 30000, "direct_benefit_monthly": 3000},
       {"ttb": 3, "ttr": 4, "ttb<ttr": True},
       {"ttb": sim20.ttb, "ttr": sim20.ttr},
       sim20.ttb == 3 and sim20.ttr == 4 and sim20.ttb < sim20.ttr)

# ============================================================================
# 21. TTB = TTR
# ============================================================================
sim21 = simulate(hist3=HIST3, baseline_monthly=BASELINE, shift_monthly=30000, thresholds=KB,
                  linked_balance=100_000_000, direct_benefit_monthly=0, horizon=12)
record("21. TTB = TTR (직접효과가 0이면 tier 변화 시점에 곧바로 누적 손익도 마이너스)",
       {"shift_monthly": 30000, "direct_benefit_monthly": 0},
       {"ttb": 3, "ttr": 3, "ttb==ttr": True},
       {"ttb": sim21.ttb, "ttr": sim21.ttr},
       sim21.ttb == 3 and sim21.ttr == 3 and sim21.ttb == sim21.ttr)

# ============================================================================
# 22. TTB 존재, TTR 없음
# ============================================================================
sim22 = simulate(hist3=HIST3, baseline_monthly=BASELINE, shift_monthly=30000, thresholds=KB,
                  linked_balance=100_000_000, direct_benefit_monthly=8000, horizon=12)
record("22. TTB는 존재(tier 하락)하지만 직접효과가 충분히 커서 TTR은 끝까지 발생하지 않음",
       {"shift_monthly": 30000, "direct_benefit_monthly": 8000},
       {"ttb": 3, "ttr": None},
       {"ttb": sim22.ttb, "ttr": sim22.ttr},
       sim22.ttb == 3 and sim22.ttr is None)

# ============================================================================
# 23. 여러 계약이 서로 다른 달에 breach
# ============================================================================
TH_EARLY = [{"min": 650000, "effect_pct_p": 0.2}, {"min": 0, "effect_pct_p": 0.0}]  # 1개월째 breach
TH_LATE = [{"min": 585000, "effect_pct_p": 0.2}, {"min": 0, "effect_pct_p": 0.0}]   # 3개월째 breach
sim_early = simulate(hist3=HIST3, baseline_monthly=BASELINE, shift_monthly=30000, thresholds=TH_EARLY,
                      linked_balance=100_000_000, horizon=12)
sim_late = simulate(hist3=HIST3, baseline_monthly=BASELINE, shift_monthly=30000, thresholds=TH_LATE,
                     linked_balance=100_000_000, horizon=12)
record("23. 여러 계약이 서로 다른 달에 breach (계약별 TTB가 독립적으로 다르게 나옴)",
       {"shift_monthly": 30000, "contracts": ["EARLY(650000 경계)", "LATE(585000 경계)"]},
       {"ttb_early": 1, "ttb_late": 3, "different_months": True},
       {"ttb_early": sim_early.ttb, "ttb_late": sim_late.ttb},
       sim_early.ttb == 1 and sim_late.ttb == 3 and sim_early.ttb != sim_late.ttb)

# ============================================================================
# 24. breach 후 조건 회복 가능한 케이스
# ============================================================================
TH_BUMP = [{"min": 650000, "effect_pct_p": 0.1}, {"min": 600000, "effect_pct_p": 0.3}, {"min": 0, "effect_pct_p": 0.1}]
sim24 = simulate(hist3=HIST3, baseline_monthly=BASELINE, shift_monthly=30000, thresholds=TH_BUMP,
                  linked_balance=100_000_000, direct_benefit_monthly=0, horizon=12)
record("24. tier가 1개월째 바뀌었다가(breach 기록=TTB=1) 3개월째 원래 tier로 회복 — TTB는 최초 시점 그대로 유지(사후에 지우지 않음), tier_effect는 실제 회복을 반영",
       {"thresholds": "600000~650000 구간만 우대가 더 높은(bump) 비정상 tier표", "shift_monthly": 30000},
       {"ttb": 1, "tier_effect[1]!=tier_effect[0]": True, "tier_effect[3]==tier_effect[0](회복)": True},
       {"ttb": sim24.ttb, "tier_effect": sim24.tier_effect[:4]},
       sim24.ttb == 1 and sim24.tier_effect[1] != sim24.tier_effect[0] and sim24.tier_effect[3] == sim24.tier_effect[0])

# ============================================================================
# 25. 동일 입력 동일 결과 deterministic 확인
# ============================================================================
run_a = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_MULTI_DIFF, planned_x=5000,
                           uncertainty_scenarios=UNC, linked_balance=100_000_000, direct_benefit_monthly=0)
run_b = compute_safe_zone(hist3=HIST3, baseline_monthly=BASELINE, rules=RULES_MULTI_DIFF, planned_x=5000,
                           uncertainty_scenarios=UNC, linked_balance=100_000_000, direct_benefit_monthly=0)
record("25. 동일 입력 → 동일 결과 (deterministic, 난수/시각 의존 없음)",
       {"same_call_twice": True}, "identical", "identical" if asdict(run_a) == asdict(run_b) else "DIFFERENT",
       asdict(run_a) == asdict(run_b))


# ---- 결과 저장 + 요약 ----
evidence_path = os.path.join(os.path.dirname(__file__), "safezone_v12_evidence.json")
with open(evidence_path, "w", encoding="utf-8") as f:
    json.dump(evidence, f, ensure_ascii=False, indent=2, default=str)

print(f"\n{passed} passed, {failed} failed  (증거 저장: {evidence_path})")
if failed:
    raise SystemExit(1)
