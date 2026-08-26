# -*- coding: utf-8 -*-
"""System B/C 컴파일러 — 약관 원문 → blind25_fixed.ExtendedRuleSchema(14필드).

박승렬이 준 세 파일(ai_rule.py / baseline_regex.py / blind25_fixed.py)에는
System A(정규식 기준선)와 Gate(EvidenceGate)만 있고, System B/C가 호출할
"Gemini로 14필드 넓은 스키마를 뽑는 컴파일러"는 없다. 이 파일이 그 빠진 조각이다.

**새 호출 경로를 만들지 않는다.** mvp/ai_rule.py가 이미 만든
  - google.genai SDK 호출 (_call_gemini)
  - 라이브 우선 → 실패 시 캐시 (_invoke)
  - 캐시 파일 / builtin 캐시 폴백
  - _LAST_ERROR 정직한 실패 사유 기록
을 그대로 재사용한다. ai_rule.py는 COMPILED_FIELDS 6개만 컴파일하도록 짜여 있어서
(대표사례에 필요한 최소셋이라는 팀의 명시적 설계 판단, ai_rule.py 상단 주석 참고)
DEV25 SCHEMA가 요구하는 14필드에는 못 쓴다 — 그래서 프롬프트/스키마만 넓게 새로 짜고
호출·캐시·에러 처리는 ai_rule의 내부 헬퍼(_invoke)를 그대로 부른다.

System B = compile_raw()        Gemini 출력 그대로, Gate 없음.
System C = compile_with_gate()  B의 출력을 blind25_fixed.EvidenceGate로 검증.

GEMINI_API_KEY가 없으면 (이 개발 환경처럼) "그럴듯한 가짜 응답을 지어내지" 않는다.
ai_rule.py와 같은 원칙 — 모르면 비워두고 정직하게 실패로 표시한다. 실제 DEV25 결과로
쓰려면 반드시 실제 키로 재실행해야 한다 (PROJECT_CURRENT_STATE.md §6, dev25_runner.py
자체 주석과 동일한 제약).
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from typing import Any, Dict, Optional, Tuple

ROOT = os.environ.get("AR_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "mvp"))
sys.path.insert(0, os.path.join(ROOT, "ablation"))

import ai_rule  # noqa: E402  (google.genai 호출·캐시·환각 게이트 재사용)
from blind25_fixed import ExtendedRuleSchema, EvidenceGate  # noqa: E402

PROMPT_VERSION = "wide_compiler_v1_2026-08-25"

# ── Gemini 구조화 출력 스키마 (ExtendedRuleSchema 14필드와 1:1 대응) ──────────
# 전부 문자열로 받는다. StrongRegexBaseline과 형식을 맞춰야 두 System을 같은
# EvidenceGate로 채점할 수 있다 (숫자는 문자열 안에 원문 표기 그대로 담긴다.
# 예: "100만원 이상", "0.20%" — ai_rule.ungrounded_numbers가 문자열 속 숫자를 뽑아
# 원문과 대조하므로, 값을 미리 정수로 바꾸면 접지 검사가 오히려 부정확해진다).
_WIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "rule_id": {"type": "string"},
        "target_event": {"type": "string"},
        "condition": {"type": "string"},
        "effect": {"type": "string"},
        "nested_or_conditions": {"type": "array", "items": {"type": "string"}},
        "tiers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "threshold": {"type": "string"},
                    "effect_value": {"type": "string"},
                },
            },
        },
        "window": {"type": "string"},
        "effect_value": {"type": "string"},
        "exception": {"type": "string"},
        "attribution_rule": {"type": "string"},
        "grace_period": {"type": "string"},
        "recalc_frequency": {"type": "string"},
        "cap_or_rate_floor": {"type": "string"},
        "reversible_or_retroactive_restore": {"type": "string"},
    },
}

_WIDE_PROMPT = """당신은 한국 금융상품 약관 문장을 기계가 읽을 수 있는 규칙으로
구조화하는 컴파일러입니다. 최종 금액 계산이나 PASS/REVIEW/HOLD 판정은 하지
않습니다 — 오직 아래 14개 필드로 구조화만 합니다.

rule_id             이 규칙을 식별할 짧은 이름 (없으면 비움)
target_event        이 조항이 적용되는 행동/이벤트 (예: 카드 이용실적)
condition           적용 조건 서술 (예: "최근 3개월 60만원 이상 이용")
effect              조건 충족 시 효과 서술
nested_or_conditions 조건들 사이의 OR/대체 관계가 있으면 그 목록. 없으면 빈 배열
tiers               계단형 다중 구간이면 각 구간을 {threshold, effect_value}로.
                    단일 구간이면 빈 배열로 두고 effect_value만 채운다.
window              측정 기간. 원문 표기 그대로 (예: "최근 3개월", "12개월간")
effect_value        단일 구간일 때의 우대폭/효과. 원문 표기 그대로 (예: "0.20%", "0.2%p")
exception           예외/제외 조항. 원문 표현 그대로. 없으면 비움
attribution_rule    실적 인정을 위한 귀속조건. 원문 표현 그대로. 없으면 비움
grace_period        유예 기간이 명시되어 있으면 그대로. 없으면 비움
recalc_frequency    재산정 주기가 명시되어 있으면 그대로. 없으면 비움
cap_or_rate_floor   한도(cap) 또는 최저금리(floor)가 명시되어 있으면 그대로. 없으면 비움
reversible_or_retroactive_restore  복구/소급 적용 관련 서술이 있으면 그대로. 없으면 비움

**절대 규칙**
1. 원문에 없는 숫자·조건을 지어내지 마세요. 확실하지 않으면 그 필드를 비우세요(빈 문자열/빈 배열).
2. 숫자를 담는 필드(threshold, effect_value, window, cap_or_rate_floor)는 원문에 쓰인
   표기를 그대로 옮기세요. 단위를 임의로 바꾸거나(예: "60만원"→"600000") 반올림하지 마세요.
3. tiers를 채웠으면 effect_value(단일값)는 비워두세요. 같은 정보를 두 번 넣지 마세요.

[조항 원문]
{clause}
"""


def _prompt_hash() -> str:
    return hashlib.sha256((_WIDE_PROMPT + PROMPT_VERSION).encode("utf-8")).hexdigest()[:12]


def _clean(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """빈 문자열/빈 배열/None을 걷어내고 ExtendedRuleSchema로 한 번 검증한다."""
    if not data:
        return {}

    def _stringify(v: Any) -> Any:
        # 스키마는 전부 문자열 필드인데, Gemini가 숫자처럼 보이는 값을 구조화 출력
        # 스펙과 다르게 실제 숫자 타입(0.2)으로 보낼 때가 있다. pydantic이 이걸
        # 곧바로 거부하면 그 필드 하나 때문에 전체가 날아가므로, 검증 전에
        # 문자열로 바꿔서 원래 의도(원문 표기 그대로)에 최대한 맞춘다.
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return str(v)
        return v

    trimmed: Dict[str, Any] = {}
    for k, v in data.items():
        if k not in ExtendedRuleSchema.model_fields:
            continue
        if k == "tiers" and isinstance(v, list):
            v = [{tk: _stringify(tv) for tk, tv in t.items()} if isinstance(t, dict) else t for t in v]
        elif k == "nested_or_conditions" and isinstance(v, list):
            pass
        else:
            v = _stringify(v)
        if v in (None, "", [], {}):
            continue
        trimmed[k] = v

    # 필드 하나가 스키마를 어겨도(예: tiers 안 원소 형태가 틀림) 그 필드만 버리고
    # 나머지는 살린다 — 통째로 폐기하지 않는다. (전체 한 번에 검증했다가 실패하면
    # 전부 버려지던 버그를 여기서 필드 단위로 나눠서 고쳤다.)
    result: Dict[str, Any] = {}
    for k, v in trimmed.items():
        try:
            single = ExtendedRuleSchema(**{k: v})
        except Exception:
            continue
        dumped = single.model_dump(exclude_none=True, exclude_defaults=True)
        if k in dumped:
            result[k] = dumped[k]
    return result


def compile_raw(source_text: str, rule_id: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """System B: Gemini 넓은 스키마 추출, Gate 없음.

    ai_rule._invoke를 그대로 재사용 — 라이브 우선, 실패하면 캐시, 어느 쪽인지
    source로 표시된다. 키/SDK/캐시가 전부 없으면 (None, "cache")가 돌아온다 —
    이 경우 정직하게 빈 결과 + 실패 사유를 meta에 남긴다(가짜 값으로 채우지 않는다).
    """
    t0 = time.time()
    # .format()이 아니라 치환을 쓴다 — 프롬프트 안에 {threshold, effect_value} 같은
    # 예시 중괄호가 있어서 str.format()이 이걸 플레이스홀더로 오인해 KeyError가 난다.
    prompt = _WIDE_PROMPT.replace("{clause}", source_text.strip())
    data, source = ai_rule._invoke("wide_compile", source_text, prompt, _WIDE_SCHEMA)
    latency_ms = int((time.time() - t0) * 1000)

    fields = _clean(data)
    ok = bool(fields)  # rule_id를 채우기 전에 판단 — rule_id는 우리가 넣은 fallback이지
                       # AI가 뽑은 내용이 아니므로 "추출 성공" 여부에 넣으면 안 된다.
    if rule_id and not fields.get("rule_id"):
        fields["rule_id"] = rule_id
    meta = {
        "model_name": ai_rule._MODEL if source == ai_rule.SOURCE_LIVE else f"{ai_rule._MODEL} (캐시/미실행)",
        "prompt_version": f"{PROMPT_VERSION}_{_prompt_hash()}",
        "latency_ms": latency_ms,
        "raw_output_json": data,
        "source": source,
        "accepted": "Y" if ok else "N",
        "reject_reason": None if ok else (ai_rule.last_error() or "추출된 필드 없음 (키/캐시 없음)"),
    }
    return fields, meta


def compile_with_gate(source_text: str, rule_id: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """System C: B의 출력을 blind25_fixed.EvidenceGate(ai_rule.ungrounded_numbers 기반)로 검증."""
    fields, meta = compile_raw(source_text, rule_id)
    if meta["accepted"] == "N":
        # B 단계에서 이미 추출 실패면 Gate를 다시 돌릴 대상이 없다.
        return fields, meta

    verdict = EvidenceGate.verify(fields, source_text)
    meta = dict(meta)  # B의 meta를 변형하지 않고 복사해서 갱신
    meta["accepted"] = "Y" if verdict["accepted"] else "N"
    meta["reject_reason"] = verdict["reject_reason"]
    return fields, meta


__all__ = ["compile_raw", "compile_with_gate", "PROMPT_VERSION"]


if __name__ == "__main__":
    src = ("금리특약 우대조건 - 신용체크카드 결제 실적"
           "(전전월부터 전월 중 결제실적 100만원 이상) : 연 0.20%")
    fields, meta = compile_raw(src, rule_id="SELFCHECK")
    print("compile_raw:", fields)
    print("meta:", {k: v for k, v in meta.items() if k != "raw_output_json"})
    fields2, meta2 = compile_with_gate(src, rule_id="SELFCHECK")
    print("compile_with_gate accepted:", meta2["accepted"], meta2["reject_reason"])