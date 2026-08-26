# -*- coding: utf-8 -*-
"""BLIND25 본실험 — 수정본 (2026-08-25 / 박승렬)

확정본에서 바꾼 것은 **두 군데뿐**이다. 스키마와 프롬프트는 그대로 둔다.

  1. EvidenceGate.normalize_text  →  mvp/ai_rule.ungrounded_numbers 로 교체
     사유: 기존 정규화가 `(\\d+(?:\\.\\d+)?)(억|만|천)?원?` 로 **단위 없는 맨숫자까지** 잡고
           `int(num)` 으로 잘라서, 0.3%p·0.5%p·0.1%p 가 전부 "0원" 이 된다.
           → U005(정답 0.20%)에서 0.90% / 0.10% / 0.55% / 0.99% 가 전부 accepted=True.
           우대금리는 대부분 0.1~0.5%p 대라 **금리 환각을 하나도 못 잡는다.**

  2. StrongRegexBaseline  →  ablation/baseline_regex.py v5 어댑터로 교체
     사유: 신규 패턴이 BLIND25 25건 중 **24건에서 수치를 하나도 못 뽑는다**(tier 전건 0, cap 전건 0).
           실제 약관 어투 "…100만원 이상) : 연 0.20%" 를 tier_pattern 이 못 받는다.
           v5 는 같은 25건에서 17건 추출. **약한 baseline 은 A 를 이기는 게 아니라 실험을 무효로 만든다.**

의존: mvp/ai_rule.py, ablation/baseline_regex.py  (둘 다 기존 파일, 수정하지 않음)
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# --- 기존 검증된 모듈을 그대로 쓴다 (새로 짜지 않는다) ---------------------
ROOT = os.environ.get("AR_ROOT", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "mvp"))
sys.path.insert(0, os.path.join(ROOT, "ablation"))

import ai_rule                      # noqa: E402  (28/28 통과 · 숫자 접지 검사)
import baseline_regex as v5         # noqa: E402  (v5 · 한글 수사 파서 포함)


# ==========================================
# 1. 출력 스키마 — 확정본 그대로 (변경 없음)
# ==========================================

class TierSpec(BaseModel):
    threshold: Optional[str] = Field(None, description="구간 조건 (예: 100만원 이상)")
    effect_value: Optional[str] = Field(None, description="구간별 혜택/효과 (예: 1.5%, 5000원)")


class ExtendedRuleSchema(BaseModel):
    rule_id: Optional[str] = None
    target_event: Optional[str] = None
    condition: Optional[str] = None
    effect: Optional[str] = None

    nested_or_conditions: List[str] = Field(default_factory=list, description="복합 OR 조건 목록")
    tiers: List[TierSpec] = Field(default_factory=list, description="다중 구간/티어 배열")
    window: Optional[str] = Field(None, description="산정 기간 (예: 최근 3개월)")
    effect_value: Optional[str] = Field(None, description="단일 효과 금액/비율 (예: 0.5%p, 1만원)")
    exception: Optional[str] = Field(None, description="예외/제외 조항")
    attribution_rule: Optional[str] = Field(None, description="귀속/실적 인정 기준")
    grace_period: Optional[str] = Field(None, description="유예 기간")
    recalc_frequency: Optional[str] = Field(None, description="재산정 주기")
    cap_or_rate_floor: Optional[str] = Field(None, description="한도(Cap) 또는 최저 금리(Floor)")
    reversible_or_retroactive_restore: Optional[str] = Field(None, description="복구/소급 적용 여부")


# 값이 원문에 실재해야 하는 필드. 서술 필드(condition/effect/attribution_rule 등)는
# 문장이라 숫자 접지 대상이 아니다 — 숫자를 담는 필드만 검사한다.
_NUMERIC_FIELDS = ("effect_value", "threshold", "window", "cap_or_rate_floor")


# ==========================================
# 2. Evidence Gate — ai_rule 로 교체
# ==========================================

class EvidenceGate:
    """원문에 글자로 존재하지 않는 숫자를 잡는다.

    `ai_rule.ungrounded_numbers` 가 `600000 → 600,000 / 60만 / 60만원` 같은
    한국어 표기 변형을 전부 만들어 대조한다. 소수점을 잘라내지 않는다.
    """

    @staticmethod
    def _flatten(obj: Any, out: Dict[str, str], prefix: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    EvidenceGate._flatten(v, out, prefix)
                elif k in _NUMERIC_FIELDS and isinstance(v, str) and v.strip():
                    out[f"{prefix}{k}#{len(out)}"] = v
        elif isinstance(obj, list):
            for item in obj:
                EvidenceGate._flatten(item, out, prefix)

    @classmethod
    def verify(cls, extracted_data: Dict[str, Any], source_text: str) -> Dict[str, Any]:
        fields: Dict[str, str] = {}
        cls._flatten(extracted_data, fields)

        bad = ai_rule.ungrounded_numbers(fields, source_text)
        if bad:
            detail = ", ".join(f"{k.split('#')[0]}={n:g}" for k, n in bad)
            return {
                "accepted": False,
                "reject_reason": f"Material values not grounded in source text: {detail}",
                "data": None,
            }

        # required 필드가 원문에 없어 null 인 것은 실패가 아니다 (RUN_RULES `null 처리`).
        return {"accepted": True, "reject_reason": None, "data": extracted_data}


# ==========================================
# 3. Regex Baseline — baseline_regex v5 어댑터
# ==========================================

_WINDOW_KO = {"D": "일", "M": "개월", "Y": "년"}


def _window_text(code: Optional[str]) -> Optional[str]:
    """v5 의 `3M` 같은 코드를 스키마의 사람이 읽는 문자열로 되돌린다."""
    if not code:
        return None
    m = re.fullmatch(r"(\d+)([DMY])", str(code))
    return f"{m.group(1)}{_WINDOW_KO[m.group(2)]}" if m else str(code)


def _num_text(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


class StrongRegexBaseline:
    """A 계열. 결정론적 파서 — LLM 없음."""

    VERSION = f"baseline_regex {v5.VERSION} + adapter 2026-08-25"

    @staticmethod
    def extract(text: str) -> Dict[str, Any]:
        p = v5.parse(text)
        result = ExtendedRuleSchema().model_dump()

        result["window"] = _window_text(p.get("window"))
        result["exception"] = p.get("exception")
        result["attribution_rule"] = p.get("attribution_rule")

        tiers = v5.parse_tiers(text)
        if tiers:
            result["tiers"] = [
                {"threshold": _num_text(t.get("threshold")),
                 "effect_value": _num_text(t.get("effect_value"))}
                for t in tiers
            ]
        else:
            result["effect_value"] = _num_text(p.get("effect_value"))

        # v5 의 threshold 는 금액 정수. 단일 구간일 때만 의미가 있다.
        if not tiers and p.get("threshold") is not None:
            result["condition"] = _num_text(p.get("threshold"))

        return result


# ==========================================
# self-check — 확정본이 놓친 것만 고정한다
# ==========================================

def _selfcheck() -> None:
    src = ("금리특약 우대조건 - 신용체크카드 결제 실적"
           "(전전월부터 전월 중 결제실적 100만원 이상) : 연 0.20%")

    assert EvidenceGate.verify({"effect_value": "0.20"}, src)["accepted"] is True
    for fake in ("0.90", "0.10", "0.55", "0.99"):
        r = EvidenceGate.verify({"effect_value": fake}, src)
        assert r["accepted"] is False, f"환각 {fake} 를 통과시켰다"

    # tiers 안쪽도 검사된다
    bad_tier = {"tiers": [{"threshold": "1000000", "effect_value": "7.77"}]}
    assert EvidenceGate.verify(bad_tier, src)["accepted"] is False

    # baseline 이 실제로 수치를 뽑는다
    out = StrongRegexBaseline.extract(src)
    assert out["effect_value"] == "0.2", out

    print("self-check 통과 — 환각 4건 차단 · tier 내부 검사 · baseline 추출 확인")


if __name__ == "__main__":
    _selfcheck()
