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

from rule_store import RuleStore
from action_interpreter import interpret
from engine import simulate, safe_limit, decide, evaluate_discrete_rule, tier_lookup

APP_START = time.time()
AR_MODE = os.environ.get("AR_MODE", "DEMO")

app = Flask(__name__, static_folder="static")
store = RuleStore()

# 데모 기본값 (사용자가 안 채우면 이 값 사용 — 업무지시서 §5 데모 시나리오)
DEFAULT_HIST3 = [220000, 220000, 220000]
DEFAULT_BASELINE = 220000


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

    if not action_type:
        return jsonify({"decision": "REVIEW", "reason": "행동 유형이 확인되지 않았습니다.",
                         "matched_rules": []}), 200

    matched = store.match(action_type, institution)
    freshness_ok = store.all_fresh([r["rule_id"] for r in matched]) if matched else False
    rule_matched = len(matched) > 0

    if not rule_matched:
        result = decide(freshness_ok=True, inputs_sufficient=True, rule_matched=False)
        return jsonify({**result, "matched_rules": []})

    # CARD_SPEND_SHIFT — 연속 시뮬레이션 (Safe Limit/TTB/TTR)
    if action_type == "CARD_SPEND_SHIFT":
        rule = next((r for r in matched if r.get("tiers") and "min_won" in r["tiers"][0]), matched[0])
        thresholds = _rule_to_thresholds(rule)
        if not thresholds:
            return jsonify({"decision": "REVIEW",
                             "reason": "매칭된 규칙에 구간 정보가 없어 자동 계산할 수 없습니다.",
                             "matched_rules": [rule["rule_id"]]})
        amount = body.get("amount_monthly")
        if amount is None or amount <= 0:
            result = decide(freshness_ok=freshness_ok, inputs_sufficient=False, rule_matched=True)
            return jsonify({**result, "matched_rules": [rule["rule_id"]]})

        hist3 = body.get("hist3") or DEFAULT_HIST3
        baseline = body.get("baseline_monthly") or DEFAULT_BASELINE
        linked_balance = body.get("linked_balance", 100_000_000)
        direct_benefit = body.get("direct_benefit_monthly", 0)

        sim = simulate(hist3=hist3, baseline_monthly=baseline, shift_monthly=amount,
                        thresholds=thresholds, linked_balance=linked_balance,
                        direct_benefit_monthly=direct_benefit)
        sl = safe_limit(hist3=hist3, baseline_monthly=baseline, thresholds=thresholds)
        result = decide(freshness_ok=freshness_ok, inputs_sufficient=True, rule_matched=True, sim=sim)
        return jsonify({
            **result,
            "matched_rules": [rule["rule_id"]],
            "safe_limit_won": sl,
            "ttb_months": sim.ttb,
            "ttr_months": sim.ttr,
            "current_tier_pct_p": sim.tier_effect[0],
            "evidence": {"source_url": rule["source_url"], "verified_at": rule["verified_at"]},
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
    return jsonify({
        **result,
        "matched_rules": [rule["rule_id"]],
        "evidence": {"source_url": rule["source_url"], "verified_at": rule["verified_at"]},
    })


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
