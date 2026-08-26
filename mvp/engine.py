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
        return DiscreteEffect(violation=False, exception_applied=True,
                               reason=f"예외 조항이 적용됩니다: {exception_text}")
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
