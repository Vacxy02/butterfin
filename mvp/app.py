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

# 2026-09-05 (V7 FIX 7-A): "이 MVP가 사용자의 모든 금융계약을 검증한다"는 오해를
# 막기 위해, 모든 /api/evaluate 응답에 공통으로 실어 보내는 판정 범위 고지문.
# HANA_HISTORY_SAVINGS의 PASS가 "해지 전체가 무조건 안전하다"로 오독되는 것을
# 포함해, 판정이 "매칭된 등록 규칙 + 입력/시나리오 범위"에 한정된다는 걸 항상
# 명시한다(판정 로직 자체는 바꾸지 않는 순수 고지 문구).
SCOPE_NOTE = "본 판정은 아래에 매칭된 등록 규칙과 입력/시나리오 범위 기준입니다."

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


MAX_INTERPRET_TEXT_LEN = 500  # 독립감사 F27: 서버단 방어(클라이언트 maxlength는 우회 가능)


@app.route("/api/interpret", methods=["POST"])
def api_interpret():
    body = request.get_json(force=True, silent=True) or {}
    text = body.get("text", "")
    if not isinstance(text, str):
        text = ""
    if len(text) > MAX_INTERPRET_TEXT_LEN:
        text = text[:MAX_INTERPRET_TEXT_LEN]
    delta, meta = interpret(text)
    # 2026-09-05 (독립감사 F27): action_interpreter.interpret()의 주석은 "원문 예외
    # 메시지는 서버 쪽 meta['error']에만 남겨서 로그/디버깅에 쓴다"고 말하지만, 실제로는
    # 이 meta 딕셔너리가 그대로 jsonify되어 브라우저 네트워크 탭에 노출되고 있었다 —
    # 코드 주석의 의도와 실제 동작이 어긋난 정보 노출 결함. 서버 로그에는 남기고
    # (print), 클라이언트로는 일반화된 문구만 내려준다. AI/판정 로직은 안 바꿨다.
    if meta.get("error"):
        print(f"[api_interpret] AI 호출 실패(서버 로그 전용): {meta['error']}")
        meta = {k: v for k, v in meta.items() if k != "error"}
    return jsonify({"delta": delta.to_dict(), "meta": meta})


def _rule_to_thresholds(rule: dict):
    return [{"min": t["min_won"], "effect_pct_p": t["effect_pct_p"]} for t in rule.get("tiers", [])]


def _safe_float(value):
    """2026-09-05 (독립감사 F23): amount_monthly="50000"처럼 문자열/이상한 타입이
    들어오면 `amount <= 0` 비교에서 TypeError가 나서 500으로 죽었다(fail-closed
    원칙 위반 — REVIEW 대신 서버 에러). 숫자로 못 바꾸면 None을 돌려주고, 호출부가
    None을 "값 없음"과 동일하게 취급해 REVIEW로 안전 종료하게 한다. 판정 로직/
    임계값은 전혀 안 바꿨다 — 타입 방어만 추가."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    # (사용자 지적 반영, 2026-08-28).
    # 2026-09-05 (V7 FIX 1, strict/fail-closed matching): rule_store.match()가 이제
    # institution/product 불일치를 fallback 없이 정직하게 0건으로 반환하므로, 여기서는
    # 그 0건을 그대로 REVIEW로 처리하기만 하면 된다(임의 후보로 되돌아가지 않음).
    matched = store.match(action_type, institution, product)
    freshness_ok = store.all_fresh([r["rule_id"] for r in matched]) if matched else False
    rule_matched = len(matched) > 0

    if not rule_matched:
        result = decide(freshness_ok=True, inputs_sufficient=True, rule_matched=False)
        return jsonify({**result, "matched_rules": [],
                         "scope_note": SCOPE_NOTE})

    # 2026-09-05 (V7 FIX 1, bullet 2): 이산형(PRODUCT_TERMINATION/PAYMENT_ACCOUNT_
    # CHANGE/SALARY_ACCOUNT_CHANGE)은 institution/product가 충분히 안 좁혀져서
    # 후보가 2개 이상이면 자동판정(matched[0])하지 않고 REVIEW로 "어떤 계약인지
    # 특정해달라"고 요청한다. CARD_SPEND_SHIFT는 다르다 — engine.compute_safe_zone이
    # qualifying_rules(구간정보가 있는 후보) 전부를 함께 계산해 "가장 엄격한 계약"을
    # binding_constraints로 명시적으로 밝히는 구조라서(하나를 조용히 골라 나머지를
    # 버리는 게 아니라, 다중계약을 다 반영해서 계산한다) 여기서는 게이트를 걸지
    # 않는다 — 아래 CARD_SPEND_SHIFT 분기에서 qualifying_rules 필터/계산 로직이
    # 그대로 이 역할을 한다.
    if action_type != "CARD_SPEND_SHIFT" and len(matched) > 1:
        candidates = [
            {"rule_id": r["rule_id"], "institution": r.get("institution"), "product": r.get("product")}
            for r in matched
        ]
        return jsonify({
            "decision": "REVIEW",
            "reason": "영향받는 보유계약을 특정해주세요.",
            "matched_rules": [r["rule_id"] for r in matched],
            "candidates": candidates,
            "scope_note": SCOPE_NOTE,
        })

    # CARD_SPEND_SHIFT — 연속 시뮬레이션 (Safe Zone/TTB/TTR). 수학 v1.2(2026-08-28):
    # 매칭된 계약(규칙) 전부를 engine.compute_safe_zone에 넘겨서 "다중계약 중 가장
    # 엄격한 계약이 무엇인지(binding_constraints)"까지 계산한다 — 예전엔 첫 번째로
    # 매칭된 규칙 하나만 썼다.
    if action_type == "CARD_SPEND_SHIFT":
        qualifying_rules = [r for r in matched if r.get("tiers") and "min_won" in r["tiers"][0]]
        if not qualifying_rules:
            return jsonify({"decision": "REVIEW",
                             "reason": "매칭된 규칙에 구간 정보가 없어 자동 계산할 수 없습니다.",
                             "matched_rules": [r["rule_id"] for r in matched],
                             "scope_note": SCOPE_NOTE})
        amount = _safe_float(body.get("amount_monthly"))
        if amount is None or amount <= 0:
            result = decide(freshness_ok=freshness_ok, inputs_sufficient=False, rule_matched=True)
            return jsonify({**result, "matched_rules": [r["rule_id"] for r in qualifying_rules],
                             "scope_note": SCOPE_NOTE})

        # 2026-09-05 (V7 FIX 6): Safe Zone/TTB/TTR 계산의 핵심 입력인 hist3(최근
        # 3개월 카드실적)와 baseline_monthly(향후 월 실적 가정)를 사용자가 안 주면
        # 대표 시나리오값을 쓴다 — 이 값이 Safe Limit 20,000원을 만드는 핵심
        # 상태인데, 지금까지 linked_balance 가정만 화면에 보이고 이 값들은 거의
        # 안 보였다. hist3_assumed/baseline_assumed로 명시해서 응답에 함께 싣는다
        # (linked_balance_assumed와 동일한 패턴).
        hist3_provided = body.get("hist3")
        hist3_assumed = not hist3_provided
        hist3 = hist3_provided or DEFAULT_HIST3
        baseline_provided = body.get("baseline_monthly")
        baseline_assumed = not baseline_provided
        baseline = baseline_provided or DEFAULT_BASELINE
        # 2026-09-05: linked_balance(연계 계약 잔액)는 지금까지 화면이 아예 보내주는
        # 값이 없어서 매번 아래 기본값(1억원)을 무조건 썼다 — 그 결과 연쇄효과(L)가
        # 실제 사용자 잔액과 무관하게 항상 같은 가정 위에서만 계산되는 구조적 문제가
        # 있었다(동학 지적, 2026-09-05). 이제 문장에서 잔액이 명시적으로 추출되면
        # (action_interpreter.linked_balance_won) 프론트가 그 값을 body.linked_balance로
        # 실어 보낸다 — 그 경우에만 실제 값을 쓰고, 그렇지 않으면 여전히 1억원을
        # 가정하되 linked_balance_assumed=True로 명시해서 화면이 "가정값"이라고
        # 보여줄 수 있게 한다(값을 만들어내되 숨기지 않는다는 원칙).
        # F23: 음수/문자열처럼 말이 안 되는 linked_balance가 들어오면(예: 실수로
        # -1000000) 그대로 계산에 흘려보내지 않고 "안 준 것과 동일"하게 취급해
        # 안전한 가정값으로 대체한다 — 크래시 대신 fail-closed.
        linked_balance_provided = _safe_float(body.get("linked_balance"))
        if linked_balance_provided is not None and linked_balance_provided < 0:
            linked_balance_provided = None
        linked_balance_assumed = linked_balance_provided is None
        linked_balance = linked_balance_provided if linked_balance_provided is not None else 100_000_000
        direct_benefit = _safe_float(body.get("direct_benefit_monthly", 0)) or 0

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
                "hist3": {"value": hist3, "unit": "원", "assumed": hist3_assumed},
                "baseline_monthly": {"value": baseline, "unit": "원", "assumed": baseline_assumed},
                "scenario_note": "대표 시나리오 가정: 최근 3개월 카드실적 22만원/22만원/22만원, 향후 월 22만원 (미입력 시 사용)",
            },
            "scope_note": SCOPE_NOTE,
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
    # 2026-09-05 (V7 FIX 1): 위에서 이미 len(matched) > 1이면 REVIEW로 걸러졌으므로,
    # 여기 도달했다는 건 후보가 정확히 1개로 특정됐다는 뜻이다 — matched[0]가 더 이상
    # "여럿 중 임의 선택"이 아니라 "유일하게 특정된 계약"이다.
    rule = matched[0]

    # 2026-09-05 (V7 FIX 2, exception gating): exception_condition_met 체크값은
    # rule에 실제 공식 행동예외(rule["exception"])가 있을 때만 의미를 갖는다 —
    # SHINHYUP_SALARY/SHINHYUP_CARD_ACCOUNT/KB_SAVINGS_LOAN_HOLD처럼 exception
    # 필드가 없는 규칙에는 체크값이 와도 무시한다. KBANK_TELECOM_SAVINGS의
    # "MVNO 제외" 같은 eligibility 조건도 "행동을 면제해주는 예외"가 아니므로
    # (통신사 종류 제한이지 계좌변경 행동 자체를 면제하지 않음) 여기서 걸러진다 —
    # 이 규칙의 exception 필드가 실제로 "행동 면제"를 뜻하는 문구일 때만 적용된다.
    rule_has_real_exception = bool(rule.get("exception"))
    exception_met = bool(body.get("exception_condition_met", False)) and rule_has_real_exception

    # 2026-09-05 (V7 FIX 3, Didimdol tier fail-closed): HF_SUBSCRIPTION_DIDIMDOL은
    # 가입기간/납입회차별로 우대폭(%p)이 달라지는 구간형 규칙이다. 그 상태를 모르면서
    # tiers[0]을 임의로 골라 특정 %p(예: 0.3%p)를 확정해서 보여주는 건 근거 없는
    # 판정이다. 공식 당첨해지 exception이 적용되는 경우는 %p 특정이 필요 없는 별도
    # 경로이므로 그대로 통과시키고, 그 exception이 없고 가입기간/납입회차 정보도
    # 없는 일반 해지만 REVIEW로 fail-closed한다.
    if rule["rule_id"] == "HF_SUBSCRIPTION_DIDIMDOL" and not exception_met:
        tier_state_given = body.get("enrollment_years") is not None or body.get("payment_count") is not None
        if not tier_state_given:
            return jsonify({
                "decision": "REVIEW",
                "reason": "가입기간/납입회차 확인 필요 — 이 정보 없이는 정확한 상실 우대폭(%p)을 특정할 수 없습니다.",
                "matched_rules": [rule["rule_id"]],
                "scope_note": SCOPE_NOTE,
                "action": {"type": action_type, "amount": None, "unit": None},
                "effects": {"D": None, "L": None, "G": None, "reversal": False,
                            "reversal_reason": "가입기간/납입회차 미확인으로 구간을 특정할 수 없어 %p를 계산하지 않았습니다."},
                "condition": {
                    "baseline_effect_pct_p": None, "lost_pct_p": None, "exception_applied": False,
                    "new_product_rate_pct": None,
                    "review_note": "가입기간/납입회차 정보가 없어 tiers[0]을 임의로 선택하지 않습니다. "
                                   "해당 정보를 알려주시거나, 목적물 당첨에 따른 해지라면 그 사유를 표시해주세요.",
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
                "evidence": [{"rule_id": rule["rule_id"], "source_url": rule["source_url"], "verified_at": rule["verified_at"]}],
                "engine_meta": {"engine_version": ENGINE_VERSION, "rule_ledger_hash": RULE_LEDGER_HASH},
                "dlg": None,
                "action_reversal": False,
            })

    # 2026-09-05 (V7 FIX 7-A): HANA_HISTORY_SAVINGS의 원장 metric은 "가입 전일 기준
    # 6개월간 하나은행 상품 미보유 이력"이다 — 가입 시점에 이미 확정된 과거 사실이라,
    # 가입 이후 지금 이 상품을 해지하는 행동으로는 그 이력 자체가 절대 바뀌지 않는다
    # (미래 행동이 과거 사실을 못 바꾼다는 인과 원칙). 이 규칙 자체의 PASS 판정은
    # 맞지만, "해지 전체가 무조건 안전"이라는 오해를 막기 위해 판정범위 고지문
    # (SCOPE_NOTE)과 이 규칙 전용 causal_note를 항상 함께 보여준다.
    if rule["rule_id"] == "HANA_HISTORY_SAVINGS":
        reason = ("이 등록 규칙(가입 전 6개월 이력)은 현재 해지행동의 영향을 받지 않습니다. "
                  "해지 전체 손익을 의미하지 않습니다.")
        return jsonify({
            "decision": "PASS", "reason": reason,
            "matched_rules": [rule["rule_id"]],
            "scope_note": SCOPE_NOTE,
            "action": {"type": action_type, "amount": None, "unit": None},
            "effects": {"D": None, "L": None, "G": None, "reversal": False,
                        "reversal_reason": "D/G를 계산하지 않는 이산 조건이며, 이 조건은 애초에 이 행동으로 훼손될 수 없습니다."},
            "condition": {
                "baseline_effect_pct_p": rule.get("effect_pct_p"),
                "lost_pct_p": None,
                "exception_applied": False,
                "new_product_rate_pct": None,
                "causal_note": "가입 전 이력 조건 — 현재 행동으로는 훼손 불가",
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
            "evidence": [{"rule_id": rule["rule_id"], "source_url": rule["source_url"], "verified_at": rule["verified_at"]}],
            "engine_meta": {"engine_version": ENGINE_VERSION, "rule_ledger_hash": RULE_LEDGER_HASH},
            "dlg": None,
            "action_reversal": False,
        })

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
    # evaluate_discrete_rule()이 이미 계산해주는 rule_effect_pct_p(규칙상 우대폭)·
    # discrete.effect_lost_pct_p(위반 시 사라지는 폭)를 그대로 응답에 옮겨 적는다 —
    # 판정 로직(decide/evaluate_discrete_rule) 자체는 바꾸지 않았다.
    #
    # 2026-09-05 (V7 FIX 5): "새로 가입하려는 상품의 금리(%)" 입력창은 그대로 유지
    # 한다(절대 지시). 다만 예전처럼 `new_product_rate_pct - lost_pct_p`를 "순
    # 효과"로 계산해 ADVANTAGEOUS/DISADVANTAGEOUS/EQUAL을 매기던 로직은 제거한다 —
    # new_product_rate_pct(신규 상품의 전체 제시금리 %)와 lost_pct_p(기존 계약 한
    # 우대항목의 상실폭 %p)는 서로 다른 기준의 값이라 단순 차감이 "경제적 순효과"를
    # 의미하지 않는다(README V7 FIX 5). 사용자가 입력한 값은 그대로 에코해서 화면에
    # 보여주되, 두 값을 비교/차감한 파생 판정은 만들지 않는다.
    new_product_rate_pct = None
    raw_new_rate = body.get("new_product_rate_pct")
    if raw_new_rate is not None:
        try:
            new_product_rate_pct = float(raw_new_rate)
        except (TypeError, ValueError):
            new_product_rate_pct = None
    evidence = [{"rule_id": rule["rule_id"], "source_url": rule["source_url"], "verified_at": rule["verified_at"]}]
    rule_effect_pct_p = rule.get("effect_pct_p") or (rule.get("tiers", [{}])[0].get("effect_pct_p") if rule.get("tiers") else None)
    return jsonify({
        **result,
        "matched_rules": [rule["rule_id"]],
        "scope_note": SCOPE_NOTE,
        "action": {"type": action_type, "amount": None, "unit": None},
        # 2026-09-05 (V7 FIX 4): Action Reversal은 D>0, G<0을 실제로 "계산"해서
        # 판정하는 개념이다(CARD_SPEND_SHIFT만 D/G를 계산). 이산형은 D/L/G 자체가
        # 없으므로 effects.reversal/action_reversal을 discrete.violation과 동일시
        # 하지 않는다 — 항상 False로 반환해 "Action Reversal=예"로 오독될 소지를
        # 없앤다. 조건 위반 여부는 아래 condition.lost_pct_p/exception_applied와
        # top-level decision(HOLD/PASS)으로 이미 정확히 표현된다.
        "effects": {"D": None, "L": None, "G": None, "reversal": False,
                    "reversal_reason": discrete.reason},
        "condition": {
            "baseline_effect_pct_p": rule_effect_pct_p,
            "lost_pct_p": discrete.effect_lost_pct_p,
            "exception_applied": discrete.exception_applied,
            # 사용자가 입력한 신규 상품 제시금리는 그대로 보여주되(FIX 5, 입력창 유지),
            # lost_pct_p와 차감한 파생 판정(net_effect_pct_p/verdict)은 만들지 않는다.
            "new_product_rate_pct": new_product_rate_pct,
            "new_product_rate_note": ("두 값은 서로 다른 금융계약의 지표이므로 단순 차감하지 않습니다. "
                                       "실제 원화 손익 비교에는 원금/잔액, 현재·신규금리, 남은 기간, "
                                       "중도해지 조건 등이 추가로 필요합니다.") if new_product_rate_pct is not None else None,
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
        "dlg": None,
        "action_reversal": False,
    })


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
