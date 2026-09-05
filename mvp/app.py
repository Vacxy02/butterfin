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
        amount = _safe_float(body.get("amount_monthly"))
        if amount is None or amount <= 0:
            result = decide(freshness_ok=freshness_ok, inputs_sufficient=False, rule_matched=True)
            return jsonify({**result, "matched_rules": [r["rule_id"] for r in qualifying_rules]})

        # 2026-09-05 (V5 Surgical, BLOCKER 7): Safe Zone/TTB/TTR 계산의 핵심 입력인
        # hist3(최근 3개월 카드실적)와 baseline_monthly(향후 월 실적 가정)는 지금까지
        # 사용자가 안 주면 조용히 대표 시나리오값(22만원 x3, 22만원)을 썼다 — 화면에는
        # 그 사실이 전혀 드러나지 않아서, "Safe Zone 0~2만원"이 어디서 나온 숫자인지
        # 심사위원이 알 수 없었다(README V5 BLOCKER 7). linked_balance_assumed와 같은
        # 패턴으로, 대표 시나리오값을 썼는지 여부를 hist3_assumed/baseline_assumed로
        # 명시해서 결과에 함께 실어 보낸다.
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
    #
    # 2026-09-05 (V5 Surgical, BLOCKER 1 / F02): 예전엔 institution/product를 안 줘서
    # (혹은 줘도) 후보가 여러 개 남으면 그냥 matched[0](배열 순서상 첫 번째)을 골라서
    # "그 계약"이라고 확정 판정(HOLD/PASS)했다 — 사용자가 실제로 어떤 계약을 말한
    # 건지 한 번도 확인하지 않고 임의로 하나를 골라 confident한 결과를 내는 위험한
    # 동작이었다(독립감사 F02). 이제 후보가 정확히 1개일 때만 자동판정하고, 2개
    # 이상이면 "어떤 계약인지 특정해달라"는 REVIEW로 fail-closed한다. 예전 "상품
    # 미지정 해지 → KB 규칙 HOLD" 같은 골든 데모가 이 변경으로 깨질 수 있는데, 이는
    # 알고 하는 것이다(동학 2026-09-05 명시적 지시: "오래된 골든 데모를 보존하려고
    # P0를 남기지 마") — 그 데모는 새 동작(REVIEW+후보목록)에 맞춰 문서를 다시 쓴다.
    if len(matched) > 1:
        candidates = [
            {"rule_id": r["rule_id"], "institution": r.get("institution"), "product": r.get("product")}
            for r in matched
        ]
        return jsonify({
            "decision": "REVIEW",
            "reason": ("이 행동에 해당하는 등록 규칙이 여러 건(" + str(len(matched)) + "건) 있어 "
                       "어떤 계약인지 자동으로 특정할 수 없습니다. 은행/상품명을 함께 알려주세요."),
            "matched_rules": [r["rule_id"] for r in matched],
            "candidates": candidates,
            "action": {"type": action_type, "amount": None, "unit": None},
            "effects": {"D": None, "L": None, "G": None, "reversal": False,
                        "reversal_reason": "여러 계약 후보 중 하나로 특정되지 않아 판정을 계산하지 않았습니다."},
            "condition": None,
            "safety": {
                "nominal_safe_limit": None, "robust_safe_limit": None, "robust_status": "NOT_APPLICABLE",
                "robust_safe_zone": {"min": None, "max": None},
                "warning_zone": {"min_exclusive": None, "max_inclusive": None}, "warning_status": "NOT_APPLICABLE",
                "current_zone": "NOT_APPLICABLE", "binding_constraints": [],
                "financial_cliff": None, "cliff_status": "NOT_APPLICABLE",
                "optimal_safe_range": None, "optimal_status": "NOT_APPLICABLE",
            },
            "time": {"TTB": None, "TTR": None, "unit": None},
            "evidence": [],
            "engine_meta": {"engine_version": ENGINE_VERSION, "rule_ledger_hash": RULE_LEDGER_HASH},
            "dlg": None,
            "action_reversal": False,
        })

    rule = matched[0]

    # 2026-09-05 (독립감사 F16 — 인과관계 재검증): HANA_HISTORY_SAVINGS의 원장 metric은
    # "가입 전일 기준 6개월간 하나은행 상품 미보유 이력"이다 — 가입 시점에 이미 확정된
    # 과거 사실이라, 가입 이후 지금 이 상품을 해지하는 행동으로는 그 이력 자체가 절대
    # 바뀌지 않는다(미래 행동이 과거 사실을 못 바꾼다는 단순한 인과 원칙). 기존 코드는
    # 이 규칙도 다른 이산 규칙과 똑같이 action_removes_condition=True로 처리해서 해지만
    # 하면 무조건 HOLD를 내는 잘못된 판정을 하고 있었다 — 이건 값을 새로 지어내는 게
    # 아니라 오히려 근거 없는 HOLD(false HOLD)를 없애는 수정이다. 다른 7개 규칙에는
    # 영향 없음(이 규칙만 가입 전 확정 이력이라는 특수 구조라 별도 처리가 맞다).
    if rule["rule_id"] == "HANA_HISTORY_SAVINGS":
        # 2026-09-05 (V5 Surgical, BLOCKER 5): 인과관계 판정(이 규칙 자체는 현재
        # 해지행동의 영향을 받지 않는다) 자체는 여전히 맞다 — 가입 전 6개월 이력은
        # 이미 확정된 과거 사실이라 지금 해지로는 바뀌지 않는다. 문제는 예전 코드가
        # 이걸 "decision": "PASS"로 서비스 전체 판정을 내렸다는 점이다 — 해지에는
        # 이 규칙 하나 말고도 다른 손익/조건이 있을 수 있는데, 전역 PASS는 "이 해지가
        # 전반적으로 안전하다"는 오해를 줄 수 있다(독립감사 F16 재검토, 동학 2026-09-05
        # 지시: "이 규칙을 데모 다양성을 위해 억지 PASS 사례로 쓰지 말 것"). 이제는
        # 이 규칙만 NOT_AFFECTED로 표시하고 decision은 REVIEW로 낮춰서, "이 조건은
        # 안전하지만 해지 전체를 검증한 건 아니다"를 명확히 한다.
        reason = ("이 등록 규칙은 현재 해지행동의 영향을 받지 않습니다. 해지 전체 손익은 "
                  "현재 지원범위에서 검증하지 않았습니다.")
        return jsonify({
            "decision": "REVIEW", "reason": reason,
            "matched_rules": [rule["rule_id"]],
            "action": {"type": action_type, "amount": None, "unit": None},
            "effects": {"D": None, "L": None, "G": None, "reversal": False,
                        "reversal_reason": "D/G를 계산하지 않는 이산 조건이며, 이 조건 자체는 이 행동으로 훼손될 수 없습니다."},
            "condition": {
                "baseline_effect_pct_p": rule.get("effect_pct_p"),
                "lost_pct_p": None,
                "exception_applied": False,
                "rule_status": "NOT_AFFECTED",
                "causal_note": "가입 전 이력 조건 — 현재 행동으로는 훼손 불가(2026-09-05 독립감사 반영)",
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

    # 2026-09-05 (V5 Surgical, BLOCKER 2 / F04): 예전엔 rule에 실제 "exception"이
    # 있든 없든 exception_condition_met=true라는 체크값만 오면 무조건 PASS로 갈 수
    # 있었다 — 예를 들어 SHINHYUP_SALARY나 KB_SAVINGS_LOAN_HOLD처럼 rule.exception
    # 필드 자체가 없는(=행동을 면제해주는 공식 예외가 존재하지 않는) 규칙에도 체크값
    # 하나로 면제를 줄 수 있는 구조였다(독립감사 F04, 동학 2026-09-05 지시: "기존
    # '급여계좌 변경 + 아무 예외 체크 → PASS' 데모는 폐기한다"). 이제는 rule에 실제
    # exception 텍스트가 있을 때만(bool(rule.get("exception"))) 체크값이 의미를
    # 갖는다 — exception이 없는 규칙은 체크값이 와도 무시한다.
    rule_has_real_exception = bool(rule.get("exception"))
    exception_met = bool(body.get("exception_condition_met", False)) and rule_has_real_exception

    # 2026-09-05 (V5 Surgical, BLOCKER 6): HF_SUBSCRIPTION_DIDIMDOL은 tiers가
    # 가입기간/납입회차별로 다른 효과(%p)를 갖는데, 사용자가 그 상태(가입기간/납입
    # 회차)를 안 주면 예전엔 그냥 tiers[0]을 임의로 골라 확정 %p(0.3%p 등)를 보여줬다
    # — 실제로는 어느 구간에 있는지 모르는 상태에서 특정 숫자를 내는 것은 근거 없는
    # 확정 판정이다(README V5 BLOCKER 6). 공식 당첨해지 exception이 적용되는 경우는
    # 그 예외 경로로 안전하게 처리하고(면제이므로 %p 특정이 필요 없음), 그 외
    # 일반 해지는 가입기간/납입회차 정보가 없으면 정확한 %p를 내지 않고 REVIEW로
    # "필요한 정보"를 안내한다.
    if rule["rule_id"] == "HF_SUBSCRIPTION_DIDIMDOL" and not exception_met:
        tier_state_given = body.get("enrollment_years") is not None or body.get("payment_count") is not None
        if not tier_state_given:
            reason = ("이 상품은 가입기간·납입회차에 따라 우대폭이 달라지는 구간형 규칙입니다. "
                      "가입기간/납입회차 정보가 없어 정확한 상실 우대폭(%p)을 특정할 수 없습니다. "
                      "해당 정보를 알려주시거나(가입기간, 납입회차), 목적물 당첨에 따른 해지라면 "
                      "그 사유를 표시해주세요.")
            return jsonify({
                "decision": "REVIEW", "reason": reason,
                "matched_rules": [rule["rule_id"]],
                "action": {"type": action_type, "amount": None, "unit": None},
                "effects": {"D": None, "L": None, "G": None, "reversal": False,
                            "reversal_reason": "가입기간/납입회차 미확인으로 구간을 특정할 수 없어 %p를 계산하지 않았습니다."},
                "condition": {
                    "baseline_effect_pct_p": None, "lost_pct_p": None, "exception_applied": False,
                    "review_note": "가입기간/납입회차 필요 — 임의로 tiers[0]을 선택하지 않습니다.",
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
    # 2026-09-05: evaluate_discrete_rule()이 이미 계산해주는 rule_effect_pct_p(현재
    # 유지 중인 우대폭)·discrete.effect_lost_pct_p(위반 시 사라지는 폭)를 지금까지는
    # 응답에 아예 안 실어서 화면이 PASS/HOLD 배지만 보고 "얼마나"를 알 수 없었다 —
    # CARD_SPEND_SHIFT만 숫자가 풍부하고 나머지 3개 유형은 밋밋해 보인다는 지적
    # (동학, 2026-09-05)의 실제 원인. 새로 값을 만들어내는 게 아니라 엔진이 이미
    # 계산해서 버리던 값을 그대로 노출하는 것뿐이라 판정 로직(decide/evaluate_discrete_
    # rule) 자체는 한 글자도 바꾸지 않았다.
    #
    # 2026-09-05 (V5 Surgical, BLOCKER 3 — 제거): 이전에는 사용자가 입력한 새 상품
    # 금리(new_product_rate_pct)와 엔진이 계산한 lost_pct_p(위반 시 사라지는 한
    # 우대항목의 %p)를 단순 뺄셈(new_product_rate_pct - lost_pct_p)해서 "순 효과"로
    # 보여줬다. 이 계산은 금융적으로 차원이 안 맞는다 — lost_pct_p는 "기존 계약의
    # 우대조건 하나"가 사라지는 폭이고, new_product_rate_pct는 보통 "신규 상품의
    # 전체 금리"이기 때문에, 서로 같은 기준의 값이 아니다(예: 기존 우대 0.1%p 상실
    # vs 신규 상품 총금리 3.5% → "+3.4%p 유리"라는 결론은 틀린 비교다). 상품 간
    # 원화 손익을 제대로 비교하려면 현재금리·신규금리·원금/잔액·남은기간·중도해지
    # 조건 등이 모두 필요하고, 이는 이번 MVP 자동계산 범위를 벗어나므로(README V5
    # BLOCKER 3, 동학 2026-09-05 지시) 이 기능 자체를 제거한다. 원금이 같다는 가정만
    # 유지한 채 계산을 남기지 않는다 — 새 비교 모델은 이번 제출에서 만들지 않는다.
    net_effect_note = ("상품 간 원화 손익 비교는 현재금리·신규금리·원금/잔액·남은기간·"
                        "중도해지 조건 등이 필요해 현재 MVP 자동계산 범위가 아닙니다.")
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
            # 2026-09-05 (V5 Surgical, BLOCKER 4 / F17): "현재 유지 중인 우대폭"처럼
            # 현재 자격상태를 확정하는 표현은 이 배포가 사용자가 실제로 그 우대를
            # 지금 받고 있는지 한 번도 확인하지 않으면서도 확정적으로 들린다는
            # 문제가 있었다(독립감사 F17). 필드명(baseline_effect_pct_p)은 기존
            # 클라이언트/테스트 호환을 위해 유지하되, 화면 문구는 index.html에서
            # "규칙상 우대폭(현재 적용 여부 미확인)"처럼 비확정 표현으로 바꾼다 —
            # 이 note 필드가 그 비확정성을 API 레벨에서도 명시한다.
            "baseline_effect_pct_p": rule_effect_pct_p,
            "baseline_effect_note": "규칙상 우대폭입니다 — 현재 실제로 이 우대를 받고 있는지는 확인하지 않았습니다.",
            "lost_pct_p": discrete.effect_lost_pct_p,
            "exception_applied": discrete.exception_applied,
            "net_effect_note": net_effect_note,
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
