"""
Deterministic counterfactual engine.

고정 수학 (PROJECT_CURRENT_STATE.md §2):
    G_T(a) = V_T(S^a) - V_T(S)          # 행동 a를 했을 때와 안 했을 때 전체 상태가치 차
    G_T = D_T + L_T                      # 직접효과 + 연쇄효과(다른 계약 영향)
    L_T = G_T - D_T
    Reversal := D_T > 0 and G_T < 0      # "당장은 이득인데 전체로는 손해"인 경우만

    Safe Limit  : 0부터 x까지 전 구간이 보호조건(tier 유지)을 만족하는 최대 경계
    TTB         : 첫 불리한 계약조건 breach(=tier 자체가 바뀌는) 시점
    TTR         : 누적 whole-state 경제효과가 처음 음수가 되는 시점

이 파일은 AI가 아니다 — Gemini가 만든 규칙이든 사람이 등록한 규칙이든, 최종 금액
계산과 PASS/REVIEW/HOLD 판정은 전부 여기(순수 함수)에서만 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class SimResult:
    R: List[float]                 # rolling window 실적 시계열 (t=0..horizon)
    tier_effect: List[float]       # 각 시점의 우대폭(%p 또는 절대값), tier_effect[0]=현재
    D: List[float]                 # 직접효과 누적(cumDirect)
    L: List[float]                 # 연쇄효과(다른 계약) 누적 (cumLinked)
    G: List[float]                 # 전체 상태가치 변화 누적 = D + L
    ttb: Optional[int]             # Time-to-Breach: tier_effect가 tier_effect[0]과 처음 달라지는 t
    ttr: Optional[int]             # Time-to-Reversal: G가 처음 음수가 되는 t


def tier_lookup(thresholds: List[Dict[str, Any]], value: float) -> float:
    """thresholds = [{"min": 900000, "effect_pct_p": 0.3}, ...] (min 내림차순 정렬 가정 안 함 — 정렬해서 계산)"""
    ordered = sorted(thresholds, key=lambda t: t["min"], reverse=True)
    for t in ordered:
        if value >= t["min"]:
            return t["effect_pct_p"]
    return 0.0


def build_rolling_series(hist3: List[float], baseline_monthly: float, shift_monthly: float,
                          horizon: int = 12) -> List[float]:
    """hist3 = [m-2, m-1, m0] 실측. t=1..horizon은 baseline에서 shift_monthly를 뺀 값으로 가정."""
    spend = list(hist3)
    future = max(baseline_monthly - shift_monthly, 0.0)
    for _ in range(horizon):
        spend.append(future)
    R = []
    for t in range(0, horizon + 1):
        idx = t + 2
        R.append(spend[idx] + spend[idx - 1] + spend[idx - 2])
    return R


def simulate(
    *,
    hist3: List[float],
    baseline_monthly: float,
    shift_monthly: float,
    thresholds: List[Dict[str, Any]],
    linked_balance: float,
    linked_effect_base: str = "annual_pct_of_balance",  # 연이율 %p 를 월 단위 금액으로 환산
    direct_benefit_monthly: float = 0.0,
    horizon: int = 12,
) -> SimResult:
    """
    hist3: 최근 3개월 카드실적 등 [m-2, m-1, m0]
    baseline_monthly: 행동 없을 때 예상 월사용액
    shift_monthly: 다른 카드/계좌로 옮기는 월 금액 (행동 a)
    thresholds: tier_lookup에 넣을 구간표 (예: KB 카드실적→대출우대금리)
    linked_balance: 연동된 계약의 원금(대출잔액 등) — %p 효과를 실제 금액으로 환산하는 데 씀
    direct_benefit_monthly: 행동 a로 인한 직접 이득(다른 카드 캐시백 등), 월 고정값
    """
    R = build_rolling_series(hist3, baseline_monthly, shift_monthly, horizon)
    tier_effect = [tier_lookup(thresholds, r) for r in R]
    tier0 = tier_effect[0]

    D = [0.0]
    L = [0.0]
    G = [0.0]
    for t in range(1, horizon + 1):
        # %p 우대폭 차이를 월 금액으로: (tier[t]-tier0)/100 * balance / 12
        linked_monthly = (tier_effect[t] - tier0) / 100.0 * linked_balance / 12.0
        D.append(D[t - 1] + direct_benefit_monthly)
        L.append(L[t - 1] + linked_monthly)
        G.append(D[t] + L[t])

    ttb = None
    for t in range(1, horizon + 1):
        if tier_effect[t] != tier0:
            ttb = t
            break

    ttr = None
    for t in range(1, horizon + 1):
        if G[t] < 0:
            ttr = t
            break

    return SimResult(R=R, tier_effect=tier_effect, D=D, L=L, G=G, ttb=ttb, ttr=ttr)


def safe_limit(
    *,
    hist3: List[float],
    baseline_monthly: float,
    thresholds: List[Dict[str, Any]],
    horizon: int = 12,
    step: int = 1000,
) -> int:
    """0부터 x까지 전 구간에서 tier가 유지되는 최대 이동액 (1,000원 단위 이진탐색)."""
    tier0 = tier_lookup(thresholds, hist3[0] + hist3[1] + hist3[2])

    def holds(q: float) -> bool:
        R = build_rolling_series(hist3, baseline_monthly, q, horizon)
        return all(tier_lookup(thresholds, r) >= tier0 for r in R[1:])

    lo, hi = 0, int((baseline_monthly // step + 1) * step)
    if holds(hi):
        return hi
    while hi - lo > step:
        mid = round((lo + hi) / 2 / step) * step
        if mid in (lo, hi):
            break
        if holds(mid):
            lo = mid
        else:
            hi = mid
    return lo


DECISIONS = ["PASS", "REVIEW", "HOLD", "EXECUTION_BLOCKED"]


@dataclass
class DiscreteEffect:
    """연속 시뮬레이션이 아니라 '이 행동을 하면 이 조건을 잃는다/유지한다' 식의 이산 판정
    (PRODUCT_TERMINATION, PAYMENT_ACCOUNT_CHANGE, SALARY_ACCOUNT_CHANGE 같은 attribution/해지형
    규칙에 사용). exception이 적용되면 위반이 아니다."""
    violation: bool
    reason: str
    effect_lost_pct_p: Optional[float] = None
    exception_applied: bool = False


def evaluate_discrete_rule(*, rule_effect_pct_p: Optional[float], action_removes_condition: bool,
                            exception_condition_met: bool, exception_text: Optional[str]) -> DiscreteEffect:
    """
    예) 청약통장 해지(PRODUCT_TERMINATION) → 디딤돌 우대금리 제외, 단 '당첨' 사유 해지는 예외.
        결제계좌 변경(PAYMENT_ACCOUNT_CHANGE) → attribution 조건 상실 → 우대 제외.
    """
    if not action_removes_condition:
        return DiscreteEffect(violation=False, reason="이 행동은 해당 조건을 건드리지 않습니다.")
    if exception_condition_met:
        # 2026-09-04 수정: 매칭된 규칙에 exception 원문이 등록돼 있지 않으면(예: SHINHYUP_SALARY는
        # demo_rules.json에 "exception" 필드가 없음) exception_text가 None으로 들어와 화면에
        # "예외 조항이 적용됩니다: None"이라는 빈 값 노출 문구가 그대로 나가던 결함을 고친다 —
        # None일 때는 일반화된 문구로 대체한다.
        text = exception_text or "사용자가 체크한 예외 조건"
        return DiscreteEffect(violation=False, exception_applied=True,
                               reason=f"예외 조항이 적용됩니다: {text}")
    return DiscreteEffect(violation=True, effect_lost_pct_p=rule_effect_pct_p,
                           reason=f"조건을 더 이상 충족하지 않아 우대(%.2f%%p 상당)가 사라집니다." % (rule_effect_pct_p or 0))


def decide(*, freshness_ok: bool, inputs_sufficient: bool, rule_matched: bool,
           sim: Optional[SimResult] = None,
           discrete: Optional[DiscreteEffect] = None) -> Dict[str, str]:
    """
    PASS/REVIEW/HOLD는 "시간(TTB/TTR이 몇 개월 뒤인지) 하나만으로 나누지 않는다"
    (PROJECT_CURRENT_STATE.md §3). 대신 "현재 확보한 Verified/Fresh 정보로 위반이
    확인되는가"를 기준으로 나눈다 — 몇 개월 뒤든/즉시든 확인되면 HOLD, 확인이 안 되면
    (정보 부족/규칙 미매칭) REVIEW, 위반이 관측되지 않으면 PASS.

    sim(연속 시뮬레이션)과 discrete(이산 판정) 중 하나만 넘긴다.

    주의: 이 경계 기준은 이번 세션에서 스펙 문장을 바탕으로 새로 설계한 것이며 팀의
    실제 decide() 구현과 다를 수 있다. 확정되면 이 함수만 고치면 된다.
    """
    if not freshness_ok:
        return {"decision": "EXECUTION_BLOCKED",
                "reason": "관련 규칙이 Verified/Fresh 상태가 아닙니다. 재검증 전에는 계산을 실행하지 않습니다."}
    if not inputs_sufficient:
        return {"decision": "REVIEW", "reason": "필수 입력값이 부족합니다."}
    if not rule_matched:
        return {"decision": "REVIEW", "reason": "이 행동과 연결된 Verified/Fresh Rule을 찾지 못했습니다. 사람 확인이 필요합니다."}

    if discrete is not None:
        if discrete.violation:
            return {"decision": "HOLD", "reason": discrete.reason}
        return {"decision": "PASS", "reason": discrete.reason}

    if sim is None:
        return {"decision": "REVIEW", "reason": "계산 결과가 없습니다."}
    if sim.ttr is not None:
        return {"decision": "HOLD",
                "reason": f"현재 확보한 규칙과 데이터로, 이 행동을 유지하면 {sim.ttr}개월 뒤 전체 손익이 손실로 전환됨이 확인됩니다."}
    if sim.ttb is not None:
        return {"decision": "REVIEW",
                "reason": f"{sim.ttb}개월 뒤 우대구간 자체가 바뀝니다. 전체 손익은 아직 마이너스가 아니지만 조건 변화가 예상되어 확인이 필요합니다."}
    return {"decision": "PASS", "reason": f"{12}개월 시뮬레이션 동안 보호조건 위반이 관측되지 않았습니다."}


# ============================================================================
# 수학 v1.2 — Safe Zone 확장
# (2026-08-28, 박승렬 "02_수학_v1.2_엔진명세.md"/"03_1차원_구간판정_규칙.md" 기준)
#
# 기존 함수(SimResult/simulate/build_rolling_series/tier_lookup/safe_limit/decide 등)는
# 한 글자도 안 고쳤다 — 전부 추가만 했다. 적용 범위: tiers/thresholds가 있는 1차원
# 연속 행동(CARD_SPEND_SHIFT류)만. PRODUCT_TERMINATION 같은 이산 판정에는 이 Safe
# Zone 개념 자체가 적용되지 않는다(명세에 그런 정의가 없음).
#
# 원칙(명세 §11 "출력 철학" 그대로): 원문/상태에 없는 D, 임의의 uncertainty, 임의의
# safe buffer, 근거 없는 최적구간 — 이 넷은 절대 지어내지 않는다. 모르면 unknown /
# NOT_APPLICABLE / REVIEW로 명확히 남긴다.
# ============================================================================

ENGINE_VERSION = "engine_v1.2_safezone_2026-08-28"

ZONES = ["SAFE", "WARNING", "BREACH", "REVIEW"]

# Optimal Safe Range의 epsilon(명세 §9: "코드에 숨겨 하드코딩하지 말고 설정/명세에
# 명시"). 통화 최소단위(step)의 배수로 정의한다 — 이 폭 안의 G값은 "사실상 동급의
# 최적"으로 취급한다는 뜻. 호출자가 optimal_range_epsilon으로 직접 덮어쓸 수 있다.
DEFAULT_OPTIMAL_RANGE_EPSILON_STEPS = 10


@dataclass
class ConstraintLimit:
    """계약(규칙) 하나의 nominal 안전한도."""
    rule_id: str
    nominal_limit: int


@dataclass
class SafeZoneResult:
    nominal_safe_limit: Optional[int]
    robust_safe_limit: Optional[int]
    robust_status: str                       # CALCULATED | NOT_APPLICABLE | EMPTY_SAFE_ZONE
    robust_safe_zone: Dict[str, Optional[int]]
    warning_zone: Dict[str, Optional[int]]
    warning_status: str                      # CALCULATED | NOT_APPLICABLE (2026-09-05: "NONE" 폐지, FIX-2 되돌림)
    binding_constraints: List[str]
    current_zone: str                        # SAFE | WARNING | BREACH | REVIEW
    financial_cliff: Optional[float]
    cliff_status: str                        # CALCULATED | NOT_APPLICABLE | UNKNOWN
    optimal_safe_range: Optional[Dict[str, Optional[int]]]
    optimal_status: str                      # CALCULATED | UNKNOWN_EFFECT | NOT_APPLICABLE


def _per_rule_nominal_limit(*, hist3: List[float], baseline_monthly: float,
                             thresholds: List[Dict[str, Any]], horizon: int = 12, step: int = 1000) -> int:
    """단일 계약(규칙)의 nominal safe limit. 기존 safe_limit()을 그대로 재사용한다 —
    새 계산 경로가 아니라 같은 로직에 이름만 하나 더 붙인 것."""
    return safe_limit(hist3=hist3, baseline_monthly=baseline_monthly, thresholds=thresholds,
                       horizon=horizon, step=step)


def _empty_safe_zone_result(zone: str = "REVIEW") -> SafeZoneResult:
    return SafeZoneResult(
        nominal_safe_limit=None, robust_safe_limit=None, robust_status="NOT_APPLICABLE",
        robust_safe_zone={"min": None, "max": None},
        warning_zone={"min_exclusive": None, "max_inclusive": None}, warning_status="NOT_APPLICABLE",
        binding_constraints=[], current_zone=zone,
        financial_cliff=None, cliff_status="NOT_APPLICABLE",
        optimal_safe_range=None, optimal_status="NOT_APPLICABLE",
    )


def compute_safe_zone(
    *,
    hist3: List[float],
    baseline_monthly: float,
    rules: List[Dict[str, Any]],
    planned_x: Optional[float],
    horizon: int = 12,
    step: int = 1000,
    uncertainty_scenarios: Optional[List[Dict[str, Any]]] = None,
    linked_balance: Optional[float] = None,
    direct_benefit_monthly: Optional[float] = None,
    optimal_range_epsilon: Optional[float] = None,
) -> SafeZoneResult:
    """
    rules: 매칭된 계약(규칙) 전부 — 각 원소는 {"rule_id": str, "thresholds": [{"min":...,
    "effect_pct_p":...}, ...]}. 계약이 여러 개면 nominal_safe_limit은 그중 가장 엄격한
    (가장 작은) 값이고, binding_constraints는 그 값을 만든 계약 rule_id 전부다(동률
    포함 — 하나만 고르지 않는다, 명세 §7).

    uncertainty_scenarios: **실제로 확인된** 상태 불확실성이 있을 때만 넘긴다 — 예:
    hist3/baseline_monthly가 "이럴 수도 있다"는 대안 시나리오 목록(각 원소는 hist3/
    baseline_monthly를 override하는 dict). None(기본값)이면 이 배포에는 확인된
    불확실성 정보가 없다는 뜻이므로 robust_status="NOT_APPLICABLE"로 명확히 표시하고
    robust_safe_limit은 nominal과 같은 값으로 둔다(명세 §5 — 임의 버퍼 생성 금지,
    "값이 없으면 nominal과 동일" 정책으로 통일). 진짜로 값이 다른 게 아니라 "계산을
    안 했다"는 뜻이라는 걸 robust_status로 구분한다.

    linked_balance/direct_benefit_monthly: Financial Cliff·Optimal Safe Range 계산에
    필요한 G(x) 산출 근거. None이면(=D/G를 계산할 근거 없음) 둘 다 억지로 계산하지
    않고 cliff_status="UNKNOWN", optimal_status="UNKNOWN_EFFECT"로 남긴다(명세 §3, §9).
    """
    usable_rules = [r for r in rules if r.get("thresholds")]
    if not usable_rules:
        return _empty_safe_zone_result("REVIEW")

    # 1) 계약별 nominal limit → 전체는 최솟값, binding은 동률 전부
    per_rule = [
        ConstraintLimit(rule_id=r["rule_id"],
                         nominal_limit=_per_rule_nominal_limit(hist3=hist3, baseline_monthly=baseline_monthly,
                                                                thresholds=r["thresholds"], horizon=horizon, step=step))
        for r in usable_rules
    ]
    nominal = min(c.nominal_limit for c in per_rule)
    binding = [c.rule_id for c in per_rule if c.nominal_limit == nominal]

    # 2) robust — 실제 불확실성 시나리오가 있을 때만 계산한다
    if uncertainty_scenarios:
        scenario_limits = []
        for sc in uncertainty_scenarios:
            sc_hist3 = sc.get("hist3", hist3)
            sc_baseline = sc.get("baseline_monthly", baseline_monthly)
            sc_min = min(
                _per_rule_nominal_limit(hist3=sc_hist3, baseline_monthly=sc_baseline,
                                         thresholds=r["thresholds"], horizon=horizon, step=step)
                for r in usable_rules
            )
            scenario_limits.append(sc_min)
        robust_value = min([nominal] + scenario_limits)
        robust_status = "EMPTY_SAFE_ZONE" if robust_value <= 0 else "CALCULATED"
    else:
        robust_status = "NOT_APPLICABLE"
        robust_value = nominal

    robust_safe_zone = {"min": 0, "max": robust_value}

    # Warning Zone = (robust_value, nominal]. robust_value == nominal이면 폭 0인 구간
    # (예: "20,000원 ~ 20,000원")이 되지만, 그 값 자체(robust_value/nominal)는 실제로
    # 계산된 값이므로 null로 감추지 않고 그대로 보여준다(2026-09-05, 동학 요청으로
    # FIX-2의 "폭 0 구간→NONE 치환"을 되돌림 — 주의: 이 파일은 v1-freeze-2026-09-03
    # Freeze 대상이라 이 변경은 기존 190/190 회귀·서버검증 15/16·FINAL_UNSEEN 결과를
    # 무효화한다는 점을 동학이 확인한 뒤 적용한 것. 관련 테스트도 이 동작에 맞춰 갱신함
    # — tests/test_fix4_safezone.py).
    warning_status = "CALCULATED"
    warning_zone = {"min_exclusive": robust_value, "max_inclusive": nominal}

    # 3) 현재 계획 행동 x의 zone 판정 (03_1차원_구간판정_규칙.md 그대로)
    if planned_x is None:
        current_zone = "REVIEW"
    elif planned_x <= robust_value:
        current_zone = "SAFE"
    elif planned_x <= nominal:
        current_zone = "WARNING"
    else:
        current_zone = "BREACH"

    # 4) Financial Cliff — nominal 경계 바로 아래/위(최소단위 1개 차이)에서 12개월
    #    누적 G의 점프. binding 계약이 여럿이면 그중 첫 번째 계약 기준으로 계산한다
    #    (여러 계약의 개별 cliff까지 합성하는 건 이번 범위 밖 — 명세에 없음).
    if linked_balance is None:
        cliff_status = "UNKNOWN"
        financial_cliff = None
    else:
        search_ceiling = int((baseline_monthly // step + 1) * step)
        if nominal >= search_ceiling:
            # holds()가 탐색 상한까지 계속 참 → 이 구간엔 실제 breach 경계(불연속)가 없다
            cliff_status = "NOT_APPLICABLE"
            financial_cliff = None
        else:
            binding_rule = next(r for r in usable_rules if r["rule_id"] == binding[0])
            below = max(nominal - step, 0)
            above = nominal + step
            db = direct_benefit_monthly or 0.0
            sim_below = simulate(hist3=hist3, baseline_monthly=baseline_monthly, shift_monthly=below,
                                  thresholds=binding_rule["thresholds"], linked_balance=linked_balance,
                                  direct_benefit_monthly=db, horizon=horizon)
            sim_above = simulate(hist3=hist3, baseline_monthly=baseline_monthly, shift_monthly=above,
                                  thresholds=binding_rule["thresholds"], linked_balance=linked_balance,
                                  direct_benefit_monthly=db, horizon=horizon)
            cliff = sim_above.G[-1] - sim_below.G[-1]
            if abs(cliff) < 1e-9:
                cliff_status = "NOT_APPLICABLE"
                financial_cliff = 0.0
            else:
                cliff_status = "CALCULATED"
                financial_cliff = cliff

    # 5) Optimal Safe Range — 선택 구현(명세 §9). D/G 근거 없으면 UNKNOWN_EFFECT.
    if linked_balance is None:
        optimal_status = "UNKNOWN_EFFECT"
        optimal_safe_range = None
    elif robust_value <= 0:
        optimal_status = "NOT_APPLICABLE"
        optimal_safe_range = None
    else:
        binding_rule = next(r for r in usable_rules if r["rule_id"] == binding[0])
        eps_steps = optimal_range_epsilon if optimal_range_epsilon is not None else DEFAULT_OPTIMAL_RANGE_EPSILON_STEPS
        epsilon = eps_steps * step
        db = direct_benefit_monthly or 0.0
        xs = list(range(0, robust_value + 1, step))
        if not xs or xs[-1] != robust_value:
            xs.append(robust_value)
        g_values = []
        for x in xs:
            sim_x = simulate(hist3=hist3, baseline_monthly=baseline_monthly, shift_monthly=x,
                              thresholds=binding_rule["thresholds"], linked_balance=linked_balance,
                              direct_benefit_monthly=db, horizon=horizon)
            g_values.append((x, sim_x.G[-1]))
        g_star = max(g for _, g in g_values)
        good_xs = [x for x, g in g_values if g >= g_star - epsilon]
        optimal_status = "CALCULATED"
        optimal_safe_range = {"min": min(good_xs), "max": max(good_xs)}

    return SafeZoneResult(
        nominal_safe_limit=nominal, robust_safe_limit=robust_value, robust_status=robust_status,
        robust_safe_zone=robust_safe_zone, warning_zone=warning_zone, warning_status=warning_status,
        binding_constraints=binding, current_zone=current_zone,
        financial_cliff=financial_cliff, cliff_status=cliff_status,
        optimal_safe_range=optimal_safe_range, optimal_status=optimal_status,
    )


def reversal_explanation(*, D: float, G: float, ttr: Optional[int]) -> str:
    """Action Reversal(정의: D > 0 AND G < 0) 여부의 근거를, 상단 PASS/REVIEW/HOLD
    판정 사유(decide()의 reason — TTR/TTB 기준 문구)와 분리해서 설명하는 문구를 만든다.

    왜 필요한가(FIX-4, 02_FIX_1차원SafeZone_4개.md): decide()의 reason은 "누적 전체효과
    G가 TTR개월 뒤 음수로 전환된다"는 사실을 말하는데, 이건 Action Reversal의 엄격한
    수학적 정의(D>0 AND G<0)와 다른 이야기다. D=0인데 G<0인 사례에서 두 문구를 그냥
    나란히 보여주면 "reversal=아니오"인데 왜 "손실로 전환"이라고 하는지 모순처럼
    보인다 — 그래서 이 함수는 D/G 값을 근거로 "왜 reversal인지/아닌지"만 명시적으로
    설명하고, "언제 누적효과가 음수가 되는지"는 별도 필드(TTR)로 남겨 화면에서
    각자 다른 자리에 표시하게 한다.
    """
    reversal = D > 0 and G < 0
    if reversal:
        return (f"직접효과 D={round(D):,}원 > 0이고 전체효과 G={round(G):,}원 < 0이므로 "
                f"Action Reversal 정의(D>0, G<0)에 해당합니다 — 당장은 이득이나 전체 손익은 손실입니다.")
    if D <= 0 and G < 0 and ttr is not None:
        return (f"직접효과 D={round(D):,}원이 0 이하이므로 Action Reversal 정의(D>0, G<0)에는 "
                f"해당하지 않습니다. 다만 누적 전체효과(G)는 {ttr}개월 뒤 음수로 전환됩니다 — "
                f"이는 Action Reversal 여부와는 별개의 사실입니다.")
    if D <= 0 and G < 0:
        return (f"직접효과 D={round(D):,}원이 0 이하이므로 Action Reversal 정의(D>0, G<0)에는 "
                f"해당하지 않습니다. 전체효과 G={round(G):,}원도 음수이지만, 이는 D>0인 이득이 "
                f"나중에 반전된 것이 아니라 처음부터 손실입니다.")
    if D > 0 and G >= 0:
        return (f"직접효과 D={round(D):,}원 > 0이고 전체효과 G={round(G):,}원도 0 이상이므로 "
                f"Action Reversal이 아닙니다.")
    return (f"직접효과 D={round(D):,}원, 전체효과 G={round(G):,}원 — 손실 전환이 관측되지 않아 "
            f"Action Reversal이 아닙니다.")
