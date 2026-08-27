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

PROMPT_VERSION = "action_interpreter_v1_2026-08-25"

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
    if force_mock or not has_api_key():
        raw = _mock_interpret(text)
        raw = _double_check(raw)
        delta = TypedActionDelta(status=raw["status"], action_type=raw.get("action_type"),
                                  target_metric=raw.get("target_metric"),
                                  amount_monthly=raw.get("amount_monthly"), raw_text=text,
                                  clarifying_question=raw.get("clarifying_question"))
        return delta, {"model_name": "mock-not-gemini", "prompt_version": PROMPT_VERSION}

    try:
        result = call_gemini_json(SYSTEM_PROMPT, text)
    except GeminiError as e:
        # fail-closed: Gemini 호출이 실패해도 500으로 죽지 않고 NEED_INFO로 넘겨서
        # 사람이 2번 항목에서 행동 유형/금액을 직접 입력하는 수동 경로로 이어지게 한다.
        # 원문 예외 메시지(예: "HTTP Error 429: ...")는 내부 사정이라 공개 화면에 그대로
        # 보여주지 않는다 — 서버 쪽 meta["error"]에만 남겨서 로그/디버깅에 쓴다.
        delta = TypedActionDelta(
            status="NEED_INFO", raw_text=text,
            clarifying_question="자동 해석에 실패했습니다. 아래 2번 항목에서 행동 유형과 금액을 직접 선택해 주세요.",
        )
        return delta, {"model_name": os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
                        "prompt_version": PROMPT_VERSION, "error": str(e)}

    raw = _double_check(result["parsed"])
    delta = TypedActionDelta(status=raw.get("status", "ERROR"), action_type=raw.get("action_type"),
                              target_metric=raw.get("target_metric"),
                              amount_monthly=raw.get("amount_monthly"), raw_text=text,
                              clarifying_question=raw.get("clarifying_question"))
    return delta, {"model_name": result["model"], "prompt_version": PROMPT_VERSION,
                    "latency_ms": result["latency_ms"]}
