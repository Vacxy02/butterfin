"""
번들/자가진단 스크립트. Docker 빌드 시점에 실행되어, 계산 로직이 실제로 맞는지까지
확인한다 (파일 존재 여부만 보는 게 아니라 "계산 결과가 맞는가"까지 검사한다).
하나라도 실패하면 0이 아닌 코드로 종료해 빌드를 막는다 — 런타임에 발견하면 늦으므로
빌드 시점에 잡는다.

이 build의 mvp/는 자기 완결적이다(외부 부모 폴더의 원장 CSV에 의존하지 않는다,
demo_rules.json이 이미 mvp/ 안에 있다) — 그래서 "번들 생성"의 의미는 파일 복사가
아니라 자가진단이다.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ablation"))


def check_rules_loaded() -> bool:
    from rule_store import RuleStore
    store = RuleStore()
    ok = len(store.rules) > 0
    print(f"  {'✓' if ok else '✗'} 규칙 {len(store.rules)} 개 로딩 확인")
    return ok


def check_rules_fresh() -> bool:
    from rule_store import RuleStore
    store = RuleStore()
    ok = store.all_fresh([r["rule_id"] for r in store.rules])
    print(f"  {'✓' if ok else '✗'} 전체 규칙 FRESH 상태 확인")
    return ok


def check_engine_smoke() -> bool:
    """TC01류 스모크 테스트: 업무지시서 §5 데모 시나리오 재현."""
    from engine import simulate, decide
    thresholds = [{"min": 900000, "effect_pct_p": 0.3}, {"min": 600000, "effect_pct_p": 0.2},
                  {"min": 300000, "effect_pct_p": 0.1}, {"min": 0, "effect_pct_p": 0.0}]
    sim = simulate(hist3=[220000, 220000, 220000], baseline_monthly=220000, shift_monthly=30000,
                    thresholds=thresholds, linked_balance=100_000_000)
    result = decide(freshness_ok=True, inputs_sufficient=True, rule_matched=True, sim=sim)
    ok = result["decision"] == "HOLD" and sim.ttr == 3 and sim.ttb == 3
    print(f"  {'✓' if ok else '✗'} 엔진 스모크: decision={result['decision']}, TTB={sim.ttb}, TTR={sim.ttr}")
    return ok


def check_gate_blocks_hallucination() -> bool:
    """2026-08-25 실측 버그(0.90%/0.10%/0.55%/0.99%가 정답 0.20%와 구분 안 되던 문제) 회귀 확인.
    ai_rule.py(팀 실제 코드)의 ungrounded_numbers — 숫자 접지 게이트의 핵심 함수 — 를 직접 검사한다."""
    from ai_rule import ungrounded_numbers
    source = "최근 3개월 60만원 이상 카드 이용실적이 있는 경우 우대금리 0.20%를 적용합니다."
    all_blocked = all(
        ungrounded_numbers({"effect_value": fake}, source) != []
        for fake in ("0.90", "0.10", "0.55", "0.99")
    ) and ungrounded_numbers({"effect_value": "0.20"}, source) == []
    print(f"  {'✓' if all_blocked else '✗'} Evidence Gate 환각 4건 차단 확인")
    return all_blocked


def main() -> int:
    print("번들 자가진단 시작")
    checks = [check_rules_loaded, check_rules_fresh, check_engine_smoke, check_gate_blocks_hallucination]
    results = [c() for c in checks]
    passed = sum(results)
    print(f"자가진단 {passed} / {len(checks)} 통과")
    if passed != len(checks):
        print("번들 실패 — 위 실패 항목을 고치기 전에는 배포하지 않는다.")
        return 1
    print("번들 완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
