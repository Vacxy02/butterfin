"""
웹/API 엔트리포인트. 흐름:
  사용자 행동 입력 → action_interpreter(Gemini) → Typed State Delta
  → rule_store에서 관련 Verified/Fresh Rule 매칭 → engine(deterministic)
  → Safe Limit/TTB/TTR/경제적 영향 → PASS/REVIEW/HOLD → evidence 표시

AR_MODE: 이 빌드는 항상 "DEMO" 모드로 동작한다 — 실시간 은행 페이지 스크래핑(LIVE)은
구현하지 않았다(팀 스펙에 별도 사양이 없고, 은행 사이트 점검만으로 서비스가 멈추는
위험을 피하기 위해 처음부터 스냅샷 규칙(demo_rules.json)만 사용한다). 화면에는 항상
"검증 스냅샷 기준일"을 표시한다.
"""

from __future__ import annotations

import os
import time
from flask import Flask, request, jsonify, send_from_directory

import hashlib
import json

from rule_store import RuleStore
from action_interpreter import interpret
from engine import (simulate, safe_limit, decide, evaluate_discrete_rule, tier_lookup,
                     compute_safe_zone, reversal_explanation, ENGINE_VERSION)

APP_START = time.time()
AR_MODE = os.environ.get("AR_MODE", "DEMO")

app = Flask(__name__, static_folder="static")
store = RuleStore()

# rule_ledger_hash — 지금 로딩된 demo_rules.json 내용의 해시. API 응답에 실어서
# "지금 이 판정이 어느 버전의 규칙집합을 근거로 나왔는지" 추적 가능하게 한다.
with open(store.path, "rb") as _f:
    RULE_LEDGER_HASH = hashlib.sha256(_f.read()).hexdigest()

# 데모 기본값 (사용자가 안 채우면 이 값 사용 — 업무지시서 §5 데모 시나리오)
DEFAULT_HIST3 = [220000, 220000, 220000]
DEFAULT_BASELINE = 220000

# Financial Cliff는 항상 "horizon(12개월) 누적 G의 경계 점프"이고, 화면에 보여주는
# D/L/G effects는 "as_of_month(TTR/TTB 시점, 12개월보다 이를 수 있음) 시점의 누적값"이다.
# 이 둘은 원래 서로 다른 시점 기준이라 숫자가 다를 수 있다 — 우연한 계산 오류가
# 아니라 의도된 차이다. 그걸 화면/API 응답에서 명확히 구분하려고(FIX-3,
# 02_FIX_1차원SafeZone_4개.md) horizon을 매직넘버로 여기저기 흩어두지 않고 여기
# 한 곳에서만 정의해서 compute_safe_zone()/simulate() 호출에 명시적으로 넘긴다.
HORIZON_MONTHS = 12


def _self_check() -> dict:
    checks = {
        "rules_loaded": len(store.rules) > 0,
        "rules_all_fresh": store.all_fresh([r["rule_id"] for r in store.rules]),
        "engine_importable": True,
        "ar_mode_is_demo": AR_MODE == "DEMO",
    }
    return checks


@app.route("/api/health")
def health():
    checks = _self_check()
    ok = all(checks.values())
    return jsonify({
        "status": "ok" if ok else "degraded",
        "ar_mode": AR_MODE,
        "rules_loaded": len(store.rules),
        "verified_at": store._data.get("_meta", {}).get("verified_at"),
        "self_check": checks,
        "uptime_s": round(time.time() - APP_START, 1),
        # 2026-08-28: 프론트가 "어느 상품으로 좁힐지" 드롭다운을 그릴 때 이 목록을
        # 쓴다 — demo_rules.json이 바뀌어도 프론트를 따로 안 고쳐도 되게 하기 위함.
        # institutions/products는 독립적인 두 축이다(은행명만으로는 상품을 특정할 수
        # 없어서 둘 다 필요).
        "institutions": store.known_institutions(),
        "products": store.known_products(),
    }), (200 if ok else 503)


@app.route("/api/interpret", methods=["POST"])
def api_interpret():
    body = request.get_json(force=True, silent=True) or {}
    text = body.get("text", "")
    delta, meta = interpret(text)
    return jsonify({"delta": delta.to_dict(), "meta": meta})


def _rule_to_thresholds(rule: dict):
    return [{"min": t["min_won"], "effect_pct_p": t["effect_pct_p"]} for t in rule.get("tiers", [])]


@app.route("/api/evaluate", methods=["POST"])
def api_evaluate():
    body = request.get_json(force=True, silent=True) or {}
    action_type = body.get("action_type")
    institution = body.get("institution")
    product = body.get("product")

    if not action_type:
        return jsonify({"decision": "REVIEW", "reason": "행동 유형이 확인되지 않았습니다.",
                         "matched_rules": []}), 200

    # institution과 product는 독립적으로 좁힌다 — 은행명만으로 상품을 특정할 수 없다
    # (사용자 지적 반영, 2026-08-28). 둘 다 없거나 실제 등록된 값과 안 맞으면
    # rule_store.match()의 자체 fallback으로 안전하게 전체 후보로 돌아간다.
    matched = store.match(action_type, institution, product)
    freshness_ok = store.all_fresh([r["rule_id"] for r in matched]) if matched else False
    rule_matched = len(matched) > 0

    if not rule_matched:
        result = decide(freshness_ok=True, inputs_sufficient=True, rule_matched=False)
        return jsonify({**result, "matched_rules": []})

    # CARD_SPEND_SHIFT — 연속 시뮬레이션 (Safe Zone/TTB/TTR). 수학 v1.2(2026-08-28):
    # 매칭된 계약(규칙) 전부를 engine.compute_safe_zone에 넘겨서 "다중계약 중 가장
    # 엄격한 계약이 무엇인지(binding_constraints)"까지 계산한다 — 예전엔 첫 번째로
    # 매칭된 규칙 하나만 썼다.
    if action_type == "CARD_SPEND_SHIFT":
        qualifying_rules = [r for r in matched if r.get("tiers") and "min_won" in r["tiers"][0]]
        if not qualifying_rules:
            return jsonify({"decision": "REVIEW",
                             "reason": "매칭된 규칙에 구간 정보가 없어 자동 계산할 수 없습니다.",
                             "matched_rules": [r["rule_id"] for r in matched]})
        amount = body.get("amount_monthly")
        if amount is None or amount <= 0:
            result = decide(freshness_ok=freshness_ok, inputs_sufficient=False, rule_matched=True)
            return jsonify({**result, "matched_rules": [r["rule_id"] for r in qualifying_rules]})

        hist3 = body.get("hist3") or DEFAULT_HIST3
        baseline = body.get("baseline_monthly") or DEFAULT_BASELINE
        # 2026-09-05: linked_balance(연계 계약 잔액)는 지금까지 화면이 아예 보내주는
        # 값이 없어서 매번 아래 기본값(1억원)을 무조건 썼다 — 그 결과 연쇄효과(L)가
        # 실제 사용자 잔액과 무관하게 항상 같은 가정 위에서만 계산되는 구조적 문제가
        # 있었다(동학 지적, 2026-09-05). 이제 문장에서 잔액이 명시적으로 추출되면
        # (action_interpreter.linked_balance_won) 프론트가 그 값을 body.linked_balance로
        # 실어 보낸다 — 그 경우에만 실제 값을 쓰고, 그렇지 않으면 여전히 1억원을
        # 가정하되 linked_balance_assumed=True로 명시해서 화면이 "가정값"이라고
        # 보여줄 수 있게 한다(값을 만들어내되 숨기지 않는다는 원칙).
        linked_balance_provided = body.get("linked_balance")
        linked_balance_assumed = linked_balance_provided is None
        linked_balance = linked_balance_provided if linked_balance_provided is not None else 100_000_000
        direct_benefit = body.get("direct_benefit_monthly", 0)

        by_id = {r["rule_id"]: r for r in qualifying_rules}
        rules_for_engine = [{"rule_id": r["rule_id"], "thresholds": _rule_to_thresholds(r)} for r in qualifying_rules]

        # 이 배포는 실제로 확인된 상태 불확실성(Θ) 데이터를 갖고 있지 않다(hist3/
        # baseline은 사용자가 입력한 점추정값 그대로) — 그래서 uncertainty_scenarios를
        # 넘기지 않는다. 그 결과 robust_status는 항상 NOT_APPLICABLE로 정직하게
        # 나온다(임의 버퍼를 만들지 않는다는 명세 §5 원칙).
        zone = compute_safe_zone(hist3=hist3, baseline_monthly=baseline, rules=rules_for_engine,
                                  planned_x=amount, linked_balance=linked_balance,
                                  direct_benefit_monthly=direct_benefit, horizon=HORIZON_MONTHS)

        # decide()/TTB/TTR은 여러 계약 중 가장 엄격한(binding) 계약 기준으로 계산한다 —
        # 그게 실제로 먼저 문제가 될 계약이기 때문이다.
        binding_rule = by_id[zone.binding_constraints[0]]
        sim = simulate(hist3=hist3, baseline_monthly=baseline, shift_monthly=amount,
                        thresholds=_rule_to_thresholds(binding_rule), linked_balance=linked_balance,
                        direct_benefit_monthly=direct_benefit, horizon=HORIZON_MONTHS)
        result = decide(freshness_ok=freshness_ok, inputs_sufficient=True, rule_matched=True, sim=sim)

        # D/L/G(실제 원 금액)와 Action Reversal 여부 — "왜 HOLD인지" 판정 근거가 된
        # 시점의 값을 보여준다: 위반이 확인된 시점(ttr)이 있으면 그 시점, 없고 구간
        # 변화 시점(ttb)만 있으면 그 시점, 둘 다 없으면(=PASS) horizon 누적값.
        as_of_month = sim.ttr if sim.ttr is not None else (sim.ttb if sim.ttb is not None else len(sim.G) - 1)
        D_won = round(sim.D[as_of_month])
        L_won = round(sim.L[as_of_month])
        G_won = round(sim.G[as_of_month])
        reversal = bool(sim.D[as_of_month] > 0 and sim.G[as_of_month] < 0)
        # FIX-4: "누적 전체효과가 언제 음수로 전환되는가"(TTR, 위 result/reason에 이미
        # 있음)와 "Action Reversal 정의(D>0,G<0)에 해당하는가"를 화면 문구에서 분리
        # 하기 위한, D/G 값 근거의 별도 설명 텍스트.
        reversal_reason = reversal_explanation(D=sim.D[as_of_month], G=sim.G[as_of_month], ttr=sim.ttr)

        evidence = [{"rule_id": r["rule_id"], "source_url": r["source_url"], "verified_at": r["verified_at"]}
                    for r in qualifying_rules]

        # FIX-3: Financial Cliff는 항상 HORIZON_MONTHS(12개월) 누적 G의 경계 점프값이고,
        # D/L/G는 as_of_month(TTR/TTB 시점 — 12개월보다 이를 수 있음) 시점 누적값이다.
        # 서로 다른 시점 기준이라는 걸 값만 보고는 알 수 없어서, 숫자를 value/unit/
        # horizon_months 3개로 묶어 API 응답과 화면 양쪽에서 명시한다(05_최종_반환물_목록.md
        # "engine response JSON 최소 확인키" 형식을 따름). 기존 클라이언트가 참조할 수
        # 있는 bare-number 필드는 만들지 않는다 — 이 구조가 신규이므로 구버전 호환
        # 필드는 "dlg"(아래) 하나로 유지한다.
        financial_cliff_detail = (
            {"value": round(zone.financial_cliff), "unit": "원", "horizon_months": HORIZON_MONTHS}
            if zone.financial_cliff is not None else None
        )

        return jsonify({
            **result,
            "matched_rules": [r["rule_id"] for r in qualifying_rules],
            # 05_API_응답_권장스키마.json 형식
            "action": {"type": action_type, "amount": amount, "unit": "원"},
            "effects": {
                "D": {"value": D_won, "unit": "원", "horizon_months": as_of_month},
                "L": {"value": L_won, "unit": "원", "horizon_months": as_of_month},
                "G": {"value": G_won, "unit": "원", "horizon_months": as_of_month},
                "reversal": reversal,
                "reversal_reason": reversal_reason,
                # 2026-09-05: L(연쇄효과)·G·Financial Cliff는 전부 linked_balance(연계
                # 계약 잔액)에 비례한다. 사용자가 실제 값을 안 줬으면(문장에 없었으면)
                # 이 값이 가정값(기본 1억원)이라는 걸 화면이 숨기지 않고 보여줘야 한다.
                "linked_balance": {"value": linked_balance, "unit": "원", "assumed": linked_balance_assumed},
            },
            "safety": {
                "nominal_safe_limit": zone.nominal_safe_limit,
                "robust_safe_limit": zone.robust_safe_limit,
                "robust_status": zone.robust_status,
                "robust_safe_zone": zone.robust_safe_zone,
                "warning_zone": zone.warning_zone,
                "warning_status": zone.warning_status,
                "current_zone": zone.current_zone,
                "binding_constraints": zone.binding_constraints,
                "financial_cliff": financial_cliff_detail,
                "cliff_status": zone.cliff_status,
                "optimal_safe_range": zone.optimal_safe_range,
                "optimal_status": zone.optimal_status,
            },
            "time": {"TTB": sim.ttb, "TTR": sim.ttr, "unit": "month"},
            "evidence": evidence,
            "engine_meta": {"engine_version": ENGINE_VERSION, "rule_ledger_hash": RULE_LEDGER_HASH},
            # 구버전 호환 필드 — 기존 verify_deploy.py/프론트 캐시가 참조할 수 있어 유지
            "safe_limit_won": zone.nominal_safe_limit,
            "ttb_months": sim.ttb,
            "ttr_months": sim.ttr,
            "current_tier_pct_p": sim.tier_effect[0],
            "dlg": {"as_of_month": as_of_month, "direct_won": D_won, "linked_won": L_won, "total_won": G_won},
            "action_reversal": reversal,
        })

    # PRODUCT_TERMINATION / PAYMENT_ACCOUNT_CHANGE / SALARY_ACCOUNT_CHANGE — 이산 판정
    rule = matched[0]
    exception_met = bool(body.get("exception_condition_met", False))
    discrete = evaluate_discrete_rule(
        rule_effect_pct_p=rule.get("effect_pct_p") or (rule.get("tiers", [{}])[0].get("effect_pct_p") if rule.get("tiers") else None),
        action_removes_condition=True,
        exception_condition_met=exception_met,
        exception_text=rule.get("exception"),
    )
    result = decide(freshness_ok=freshness_ok, inputs_sufficient=True, rule_matched=True, discrete=discrete)
    # 이 유형(해지/계좌변경 등 이산 판정)은 engine.py에 금액 환산 모델도, Safe Zone
    # 개념도 없다(수학 v1.2 명세는 1차원 연속 행동만 다룬다) — DiscreteEffect는 %p
    # 우대 상실만 판정한다. 값을 모르면 지어내지 않고 null/NOT_APPLICABLE로 남긴다.
    #
    # 2026-09-05: evaluate_discrete_rule()이 이미 계산해주는 rule_effect_pct_p(현재
    # 유지 중인 우대폭)·discrete.effect_lost_pct_p(위반 시 사라지는 폭)를 지금까지는
    # 응답에 아예 안 실어서 화면이 PASS/HOLD 배지만 보고 "얼마나"를 알 수 없었다 —
    # CARD_SPEND_SHIFT만 숫자가 풍부하고 나머지 3개 유형은 밋밋해 보인다는 지적
    # (동학, 2026-09-05)의 실제 원인. 새로 값을 만들어내는 게 아니라 엔진이 이미
    # 계산해서 버리던 값을 그대로 노출하는 것뿐이라 판정 로직(decide/evaluate_discrete_
    # rule) 자체는 한 글자도 바꾸지 않았다.
    dlg = None
    evidence = [{"rule_id": rule["rule_id"], "source_url": rule["source_url"], "verified_at": rule["verified_at"]}]
    rule_effect_pct_p = rule.get("effect_pct_p") or (rule.get("tiers", [{}])[0].get("effect_pct_p") if rule.get("tiers") else None)
    return jsonify({
        **result,
        "matched_rules": [rule["rule_id"]],
        "action": {"type": action_type, "amount": None, "unit": None},
        "effects": {"D": None, "L": None, "G": None, "reversal": discrete.violation,
                    "reversal_reason": discrete.reason},
        "condition": {
            "baseline_effect_pct_p": rule_effect_pct_p,
            "lost_pct_p": discrete.effect_lost_pct_p,
            "exception_applied": discrete.exception_applied,
        },
        "safety": {
            "nominal_safe_limit": None, "robust_safe_limit": None, "robust_status": "NOT_APPLICABLE",
            "robust_safe_zone": {"min": None, "max": None},
            "warning_zone": {"min_exclusive": None, "max_inclusive": None}, "warning_status": "NOT_APPLICABLE",
            "current_zone": "NOT_APPLICABLE", "binding_constraints": [rule["rule_id"]],
            "financial_cliff": None, "cliff_status": "NOT_APPLICABLE",
            "optimal_safe_range": None, "optimal_status": "NOT_APPLICABLE",
        },
        "time": {"TTB": None, "TTR": None, "unit": None},
        "evidence": evidence,
        "engine_meta": {"engine_version": ENGINE_VERSION, "rule_ledger_hash": RULE_LEDGER_HASH},
        # 구버전 호환 필드
        "dlg": dlg,
        "action_reversal": discrete.violation,
    })


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
