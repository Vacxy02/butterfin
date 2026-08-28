"""
Action Interpreter — 사용자 자연어 행동 → TypedActionDelta.

모호하면 값을 상상하지 말고 NEED_INFO로 보낸다 (PROJECT_CURRENT_STATE.md §8).
AI가 "OK"라고 자체 보고해도 그대로 믿지 않고 이중검증한다 — 예: 금액이 음수/0이면
NEED_INFO로 강등한다.
"""

from __future__ import annotations

import os
import re
from typing import Optional, Dict, Any, Tuple

from schemas import TypedActionDelta, ACTION_TYPES
from gemini_client import call_gemini_json, has_api_key, GeminiError
from rule_store import RuleStore

PROMPT_VERSION = "action_interpreter_v1_2026-08-25"

# ---------------------------------------------------------------------------
# 은행/상품명 감지 (2026-08-28 추가)
# Gemini에게 은행명을 맡기지 않는다 — AI가 자유 텍스트로 "OO은행"을 뽑으면 실제로
# 등록 안 된 은행 이름을 지어낼 수 있고, 그건 이 프로젝트 전체가 지키는 "환각 차단"
# 원칙에 어긋난다. 대신 demo_rules.json에 실제로 등록된 기관 목록(rule_store.
# known_institutions())과 정확히 대조하는 결정론적 키워드 매칭만 쓴다 — 목록에
# 없는 이름은 절대 institution으로 채우지 않는다.
# ---------------------------------------------------------------------------

INSTITUTION_ALIASES: Dict[str, list] = {
    "KB국민은행": ["kb국민은행", "kb국민카드", "국민은행", "국민카드", "kb카드", "kb은행"],
    "주택금융공사": ["주택금융공사", "주금공", "디딤돌대출", "디딤돌"],
    "케이뱅크": ["케이뱅크", "k뱅크"],
    "신협": ["신협중앙회", "신협"],
    "하나은행": ["하나은행", "하나카드", "하나적금", "하나 적금"],
}

_rule_store_singleton: Optional[RuleStore] = None


def _known_institutions() -> list:
    """rule_store에 지금 실제로 로딩된 institution 목록. 파일을 매번 다시 읽지
    않도록 모듈 안에서 한 번만 캐싱한다(단, 실패해도 죽지 않고 빈 목록으로
    안전하게 대체 — 은행명 감지는 부가 기능이지 필수 경로가 아니다)."""
    global _rule_store_singleton
    if _rule_store_singleton is None:
        try:
            _rule_store_singleton = RuleStore()
        except Exception:
            return []
    return _rule_store_singleton.known_institutions()


def _detect_institution(text: str, known: Optional[list] = None) -> Optional[str]:
    """문장에 등록된 은행/기관명이 언급돼 있으면 그 기관의 정식 명칭(rule_store의
    institution 필드와 완전히 같은 문자열)을 돌려준다. 못 찾으면 None — 아무거나
    추측해서 채우지 않는다. 별칭이 여러 개 걸리면 가장 긴(구체적인) 별칭을 우선한다
    (예: "국민" 한 글자 단위가 아니라 "국민은행"처럼 더 구체적인 걸 우선 매칭)."""
    if not text:
        return None
    if known is None:
        known = _known_institutions()
    t = text.lower()
    hits = []
    for canonical, aliases in INSTITUTION_ALIASES.items():
        if canonical not in known:
            continue  # 실제로 등록 안 된 기관은 감지 대상에서 제외
        for alias in aliases:
            if alias in t:
                hits.append((len(alias), canonical))
    if not hits:
        return None
    hits.sort(reverse=True)
    return hits[0][1]


# ---------------------------------------------------------------------------
# 상품명 감지 (2026-08-28 추가, 사용자 지적 반영)
# 은행명만으로는 상품을 특정할 수 없다 — 한 은행이 여러 상품을 취급할 수도 있고
# (신협은 급여계좌/결제계좌/카드실적 세 규칙이 다 "플러스정기적금" 하나에 걸려있음),
# 반대로 같은 상품군(예: "디딤돌대출")을 여러 기관이 취급할 수도 있다(주택금융공사·
# NH농협은행 등 — 원장 37행 기준). 그래서 institution과 완전히 같은 방식으로,
# product도 독립적으로 감지해서 별도 필드에 채운다. 은행명 감지와 마찬가지로
# Gemini에게 맡기지 않고 rule_store.known_products()와 대조하는 결정론적 키워드
# 매칭만 쓴다 — 없는 상품명을 지어내지 않는다.
# ---------------------------------------------------------------------------

PRODUCT_ALIASES: Dict[str, list] = {
    "대출 금리감면 (일반 신용대출)": ["대출 금리감면", "신용대출 금리감면", "신용대출 우대금리", "일반 신용대출"],
    "내집마련 디딤돌대출": ["내집마련 디딤돌대출", "디딤돌대출", "디딤돌"],
    "주거래우대 자유적금": ["주거래우대 자유적금", "자유적금"],
    "플러스정기적금(신한카드연계형) 10차": ["플러스정기적금(신한카드연계형)", "플러스정기적금", "신한카드연계형"],
    "오늘부터, 하나 적금": ["오늘부터 하나 적금", "오늘부터, 하나 적금", "하나 적금", "하나적금"],
}


def _known_products() -> list:
    """rule_store에 지금 실제로 로딩된 product 목록. _known_institutions()와 같은
    캐싱/실패 안전 정책을 쓴다."""
    global _rule_store_singleton
    if _rule_store_singleton is None:
        try:
            _rule_store_singleton = RuleStore()
        except Exception:
            return []
    return _rule_store_singleton.known_products()


def _detect_product(text: str, known: Optional[list] = None) -> Optional[str]:
    """문장에 등록된 상품명이 언급돼 있으면 그 상품의 정식 명칭(rule_store의 product
    필드와 완전히 같은 문자열)을 돌려준다. 로직은 _detect_institution()과 동일 —
    실제 등록된 목록과 대조, 가장 긴 별칭 우선, 못 찾으면 None."""
    if not text:
        return None
    if known is None:
        known = _known_products()
    t = text.lower()
    hits = []
    for canonical, aliases in PRODUCT_ALIASES.items():
        if canonical not in known:
            continue
        for alias in aliases:
            if alias in t:
                hits.append((len(alias), canonical))
    if not hits:
        return None
    hits.sort(reverse=True)
    return hits[0][1]


SYSTEM_PROMPT = f"""너는 사용자의 한국어 문장을 아래 4가지 행동 유형 중 하나로 구조화하는
파서다. 최종 판정(PASS/REVIEW/HOLD)은 네가 하지 않는다.

행동 유형: {", ".join(ACTION_TYPES)}

JSON만 출력한다: {{"status": "OK"|"NEED_INFO"|"UNSUPPORTED",
"action_type": 유형 또는 null, "target_metric": 문자열 또는 null,
"amount_monthly": 숫자 또는 null, "clarifying_question": 문자열 또는 null}}

규칙:
- 금액/유형이 불명확하면 status="NEED_INFO"로 하고 clarifying_question에 되물을 질문을 쓴다.
  숫자를 추측하지 않는다.
- 4가지 유형에 안 맞으면 status="UNSUPPORTED".
- 다 확실하면 status="OK".
"""


def _mock_interpret(text: str) -> Dict[str, Any]:
    """키워드 기반 mock. 실제 Gemini 언어이해를 대표하지 않는다 — 파이프라인 검증용."""
    t = text or ""
    amount_m = re.search(r"(\d[\d,]*)\s*만\s*원", t)
    amount = int(amount_m.group(1).replace(",", "")) * 10_000 if amount_m else None

    if "해지" in t and ("청약" in t or "적금" in t or "예금" in t):
        return {"status": "OK", "action_type": "PRODUCT_TERMINATION",
                "target_metric": "product_hold_status", "amount_monthly": None,
                "clarifying_question": None}
    if ("카드" in t) and ("옮" in t or "이동" in t or "다른" in t):
        if amount is None:
            return {"status": "NEED_INFO", "action_type": "CARD_SPEND_SHIFT",
                     "target_metric": "rolling_3m_card_spend", "amount_monthly": None,
                     "clarifying_question": "매달 얼마를 다른 카드로 옮기실 건가요?"}
        return {"status": "OK", "action_type": "CARD_SPEND_SHIFT",
                 "target_metric": "rolling_3m_card_spend", "amount_monthly": amount,
                 "clarifying_question": None}
    if "결제계좌" in t or ("계좌" in t and "변경" in t):
        return {"status": "OK", "action_type": "PAYMENT_ACCOUNT_CHANGE",
                 "target_metric": "attribution_account", "amount_monthly": None,
                 "clarifying_question": None}
    if "급여" in t and ("계좌" in t or "이체" in t):
        return {"status": "OK", "action_type": "SALARY_ACCOUNT_CHANGE",
                 "target_metric": "salary_account", "amount_monthly": None,
                 "clarifying_question": None}
    if not t.strip():
        return {"status": "NEED_INFO", "action_type": None, "target_metric": None,
                 "amount_monthly": None, "clarifying_question": "어떤 행동을 하려고 하시는지 알려주세요."}
    return {"status": "UNSUPPORTED", "action_type": None, "target_metric": None,
             "amount_monthly": None, "clarifying_question": None}


def _double_check(d: Dict[str, Any]) -> Dict[str, Any]:
    """AI가 OK라고 해도 그대로 믿지 않는다 — 명백히 이상한 값은 NEED_INFO로 강등."""
    if d.get("status") == "OK":
        amt = d.get("amount_monthly")
        if d.get("action_type") == "CARD_SPEND_SHIFT" and (amt is None or amt <= 0):
            return {**d, "status": "NEED_INFO",
                    "clarifying_question": "옮기실 금액이 명확하지 않습니다. 월 얼마인가요?"}
        if d.get("action_type") not in ACTION_TYPES:
            return {**d, "status": "UNSUPPORTED", "action_type": None}
    return d


def interpret(text: str, force_mock: bool = False) -> Tuple[TypedActionDelta, Dict[str, Any]]:
    # 은행명/상품명 감지는 Gemini 호출 성공 여부와 무관하게 항상 같은 결정론적 로직으로
    # 한다 — mock이든 실제 Gemini든, 심지어 Gemini 호출이 실패한 경우에도 채워질 수
    # 있다(사용자가 "OO은행"/"OO적금"이라고 문장에 썼으면 실패 안내에서도 그 정보는
    # 살려서 화면에 보여줄 수 있게). 은행명만으로는 상품을 특정할 수 없어서 두 필드를
    # 독립적으로 감지한다 — product가 institution을 대신하지 않는다.
    inst = _detect_institution(text)
    prod = _detect_product(text)

    if force_mock or not has_api_key():
        raw = _mock_interpret(text)
        raw = _double_check(raw)
        delta = TypedActionDelta(status=raw["status"], action_type=raw.get("action_type"),
                                  target_metric=raw.get("target_metric"),
                                  amount_monthly=raw.get("amount_monthly"), raw_text=text,
                                  clarifying_question=raw.get("clarifying_question"),
                                  institution=inst, product=prod)
        return delta, {"model_name": "mock-not-gemini", "prompt_version": PROMPT_VERSION}

    try:
        result = call_gemini_json(SYSTEM_PROMPT, text)
    except GeminiError as e:
        # fail-closed: Gemini 호출이 실패해도 500으로 죽지 않고 NEED_INFO로 넘겨서
        # 사람이 2번 항목에서 행동 유형/금액을 직접 입력하는 수동 경로로 이어지게 한다.
        # 원문 예외 메시지(예: "HTTP Error 429: ...")는 내부 사정이라 공개 화면에 그대로
        # 보여주지 않는다 — 서버 쪽 meta["error"]에만 남겨서 로그/디버깅에 쓴다.
        delta = TypedActionDelta(
            status="NEED_INFO", raw_text=text, institution=inst, product=prod,
            clarifying_question="자동 해석에 실패했습니다. 아래 2번 항목에서 행동 유형과 금액을 직접 선택해 주세요.",
        )
        return delta, {"model_name": os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
                        "prompt_version": PROMPT_VERSION, "error": str(e)}

    raw = _double_check(result["parsed"])
    delta = TypedActionDelta(status=raw.get("status", "ERROR"), action_type=raw.get("action_type"),
                              target_metric=raw.get("target_metric"),
                              amount_monthly=raw.get("amount_monthly"), raw_text=text,
                              clarifying_question=raw.get("clarifying_question"),
                              institution=inst, product=prod)
    return delta, {"model_name": result["model"], "prompt_version": PROMPT_VERSION,
                    "latency_ms": result["latency_ms"]}
