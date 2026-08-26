"""engine.py 단위 테스트 — KB '카드실적→대출 금리감면' (Evidence Bundle KB_CARD_LOAN_STEP T1/2/3 실측)
최근 3개월 30만원→0.1%p / 60만원→0.2%p / 90만원→0.3%p
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mvp"))

from engine import simulate, safe_limit, decide, tier_lookup, build_rolling_series

THRESHOLDS = [
    {"min": 900000, "effect_pct_p": 0.3},
    {"min": 600000, "effect_pct_p": 0.2},
    {"min": 300000, "effect_pct_p": 0.1},
    {"min": 0, "effect_pct_p": 0.0},
]

HIST3 = [220000, 220000, 220000]  # 3개월 합 660,000원
BASELINE = 220000

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        print(f"✅ {name}")
        passed += 1
    else:
        print(f"❌ {name}")
        failed += 1


# T1 — tier 경계
R = build_rolling_series(HIST3, BASELINE, 30000, horizon=3)
check("T1: R0=660,000", R[0] == 660000)
check("T1: R1=630,000", R[1] == 630000)
check("T1: R2=600,000 (경계 유지)", R[2] == 600000)
check("T1: R3=570,000 (하락)", R[3] == 570000)
check("T1: tier(R0)=0.2%p", tier_lookup(THRESHOLDS, R[0]) == 0.2)
check("T1: tier(R2)=0.2%p 유지 (>=60만원)", tier_lookup(THRESHOLDS, R[2]) == 0.2)
check("T1: tier(R3)=0.1%p 하락 (<60만원)", tier_lookup(THRESHOLDS, R[3]) == 0.1)

# T2 — q=0이면 tier 불변, TTB/TTR 없음
sim0 = simulate(hist3=HIST3, baseline_monthly=BASELINE, shift_monthly=0,
                 thresholds=THRESHOLDS, linked_balance=100_000_000, horizon=12)
check("T2: q=0 → TTB 없음", sim0.ttb is None)
check("T2: q=0 → TTR 없음", sim0.ttr is None)

# T3 — linked_balance=0이면 연쇄손실 전부 0
sim_no_link = simulate(hist3=HIST3, baseline_monthly=BASELINE, shift_monthly=30000,
                        thresholds=THRESHOLDS, linked_balance=0, horizon=12)
check("T3: linked_balance=0 → L 전부 0", all(v == 0 for v in sim_no_link.L))
check("T3: linked_balance=0 → TTR 없음 (D도 0)", sim_no_link.ttr is None)

# T4 — Safe Limit: 3개월 뒤 정상상태 3*(220000-q) >= 600000 → q<=20000
sl = safe_limit(hist3=HIST3, baseline_monthly=BASELINE, thresholds=THRESHOLDS, horizon=12)
check("T4: safe_limit=20,000", sl == 20000)

# T5 — TTB <= TTR (직접효과가 커서 TTR이 늦거나 없는 경우에도 성립)
sim_big_direct = simulate(hist3=HIST3, baseline_monthly=BASELINE, shift_monthly=30000,
                           thresholds=THRESHOLDS, linked_balance=100_000_000,
                           direct_benefit_monthly=10000, horizon=12)
check("T5: TTB 존재 (tier가 3개월째 하락)", sim_big_direct.ttb == 3)
if sim_big_direct.ttr is not None:
    check("T5: TTB <= TTR", sim_big_direct.ttb <= sim_big_direct.ttr)
else:
    check("T5: TTR이 없으면 TTB<=TTR 자동 성립", True)

# T6 — TTR: 직접효과가 작으면 연쇄손실이 곧 총손익을 마이너스로
sim_small_direct = simulate(hist3=HIST3, baseline_monthly=BASELINE, shift_monthly=30000,
                             thresholds=THRESHOLDS, linked_balance=100_000_000,
                             direct_benefit_monthly=0, horizon=12)
check("T6: TTR 존재 (연쇄손실이 즉시 마이너스)", sim_small_direct.ttr is not None)
check("T6: TTR==TTB (직접효과 0일 때)", sim_small_direct.ttr == sim_big_direct.ttb)

# T7 — decide() 4갈래
check("T7: freshness 깨지면 EXECUTION_BLOCKED",
      decide(freshness_ok=False, inputs_sufficient=True, rule_matched=True, sim=None)["decision"]
      == "EXECUTION_BLOCKED")
check("T7: 입력 부족이면 REVIEW",
      decide(freshness_ok=True, inputs_sufficient=False, rule_matched=True, sim=None)["decision"]
      == "REVIEW")
check("T7: 매칭 규칙 없으면 REVIEW",
      decide(freshness_ok=True, inputs_sufficient=True, rule_matched=False, sim=None)["decision"]
      == "REVIEW")
check("T7: TTR 확인되면 HOLD (몇 개월 뒤든 상관없이)",
      decide(freshness_ok=True, inputs_sufficient=True, rule_matched=True, sim=sim_small_direct)["decision"]
      == "HOLD")
check("T7: TTB만 있고 TTR 없으면 REVIEW",
      decide(freshness_ok=True, inputs_sufficient=True, rule_matched=True, sim=sim_big_direct)["decision"]
      == "REVIEW")
check("T7: 위반 없으면 PASS",
      decide(freshness_ok=True, inputs_sufficient=True, rule_matched=True, sim=sim0)["decision"]
      == "PASS")

print(f"\n{passed} passed, {failed} failed")
if failed:
    raise SystemExit(1)
