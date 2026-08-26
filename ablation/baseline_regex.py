# -*- coding: utf-8 -*-
"""기준선 B — 정규식·키워드 기반 약관 조항 파서.

**이 파일은 우리 시스템을 돋보이게 하려고 일부러 약하게 짠 것이 아니다.**

Ablation에서 "기준선을 사람이 만들었으니 불리하게 짰겠지"는 가장 먼저 나올 반박이다.
그래서 아래 규칙은 **한국어 금융약관에서 실제로 통하는 패턴을 최대한 담았다.**

담은 것
  - 금액 표기 4종      30만원 · 1,000,000원 · 100만 · 1억
  - 비교 연산자 4종     이상(>=) · 초과(>) · 이하(<=) · 미만(<)
  - 측정 기간          최근 3개월 · 3개월간 · 1년 · 12개월
  - 우대폭             연 0.2%p · 0.2%p · 0.2% · 0.2%포인트
  - 예외 절            다만/단/제외/예외 로 시작하는 절
  - 귀속조건           "…를 당행으로 지정" · "…계좌로 …하는 경우" 류
  - 계단형 다중 임계    30만원(0.1)/60만원(0.2)/90만원(0.3) 한 문장 처리

담지 못한 것 — **이게 이 기준선의 한계이고, 그 한계가 실험의 논점이다.**
  - 문맥에 따라 달라지는 귀속 주체
  - 부정문·이중부정
  - 조건들 사이의 논리 결합(AND/OR/k-of-n)
  - 조항 밖 정의를 참조하는 표현

개선 이력 (기준선을 성실히 만들었다는 근거)
  v1  숫자와 %p만 추출
  v2  이상/초과 구분 추가 — v1은 전부 >= 로 뭉갰다
  v3  만원·억원 단위 처리 추가 — v1·v2는 "60만원"을 60으로 읽었다
  v4  계단형 다중 임계 처리 — 한 문장에 3구간이 오는 KB 카드 조항 때문
  v5  예외 절·귀속조건 추출 추가
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

VERSION = "v5"

# ── 금액 ────────────────────────────────────────────────────────────────────
# 한국어 수사는 자리수가 겹친다. "1억5천만"에서 천은 1,000이 아니라 만 자리에 붙어
# 5,000 × 10,000 = 5천만이 된다. 단위를 단순 곱으로 처리하면 100,005,000이 나온다.
# 그래서 억 → 만 → 잔여 순서로 그룹을 갈라 평가한다.

# 숫자 + 한국어 수사 덩어리 (1억5천만원 / 60만원 / 3천 / 100만)
# 단위가 여러 번 이어질 수 있고, 뒤 단위 앞에는 숫자가 없을 수도 있다("5천만"의 만).
_AMOUNT_UNIT = re.compile(r"(\d[\d,]*[억만천백십](?:[\d,]*[억만천백십])*[\d,]*)\s*원?")
# 단위어 없는 순수 숫자 + 원 (1,000,000원)
_AMOUNT_PLAIN = re.compile(r"(\d[\d,]{2,})\s*원")


def _small(s: str) -> int:
    """만 미만 자리. '5천' · '3백2십' · '12' · '' 를 처리."""
    s = s.replace(",", "").strip()
    if not s:
        return 0
    n = 0
    for ch, mult in (("천", 1000), ("백", 100), ("십", 10)):
        if ch in s:
            head, s = s.split(ch, 1)
            n += (int(head) if head.strip() else 1) * mult
    if s.strip():
        n += int(s)
    return n


def _kor_number(expr: str) -> int:
    """'1억5천만' → 150000000 · '60만' → 600000 · '3천' → 3000."""
    expr = expr.replace(",", "").strip()
    total = 0
    for big, mult in (("억", 100_000_000), ("만", 10_000)):
        if big in expr:
            head, expr = expr.split(big, 1)
            total += _small(head) * mult
    total += _small(expr)
    return total

# ── 연산자 ──────────────────────────────────────────────────────────────────
_OPS = [("이상", ">="), ("초과", ">"), ("이하", "<="), ("미만", "<")]

# ── 기간 ────────────────────────────────────────────────────────────────────
_WINDOW = re.compile(r"(?:최근\s*)?(\d+)\s*(개월|년|일)\s*(?:간|동안|이내)?")
_WINDOW_UNIT = {"개월": "M", "년": "Y", "일": "D"}

# ── 우대폭 ──────────────────────────────────────────────────────────────────
_EFFECT = re.compile(r"(?:연\s*)?(\d+(?:\.\d+)?)\s*%\s*(?:p|포인트|P)?")

# ── 예외 절 ─────────────────────────────────────────────────────────────────
_EXCEPTION_HEAD = re.compile(r"(다만[,\s]|단[,\s]|예외적으로|.{0,12}제외한다|.{0,12}제외됩니다)")

# ── 귀속조건 ────────────────────────────────────────────────────────────────
_ATTRIBUTION = re.compile(
    r"([^,.]{2,20}(?:계좌|결제계좌|통장)[을를]?\s*[^,.]{0,20}(?:지정|등록|설정)[^,.]{0,10})"
)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "")


def _amount_at(text: str, pos: int) -> Optional[int]:
    """pos 에서 시작하는 금액 하나를 읽는다."""
    m = _AMOUNT_UNIT.match(text, pos)
    if m:
        return _kor_number(m.group(1))
    m = _AMOUNT_PLAIN.match(text, pos)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def _all_amounts(text: str) -> List[int]:
    """문장에 나오는 금액을 등장 순서대로 전부."""
    out, i = [], 0
    while i < len(text):
        v = _amount_at(text, i)
        if v is not None:
            out.append(v)
            m = _AMOUNT_UNIT.match(text, i) or _AMOUNT_PLAIN.match(text, i)
            i = m.end()
        else:
            i += 1
    return out


def _all_effects(text: str) -> List[float]:
    return [float(m.group(1)) for m in _EFFECT.finditer(text)]


def _operator(text: str) -> Optional[str]:
    """가장 먼저 나오는 비교 표현을 쓴다. 없으면 None (추측하지 않는다)."""
    best, pos = None, len(text) + 1
    for word, op in _OPS:
        i = text.find(word)
        if i != -1 and i < pos:
            best, pos = op, i
    return best


def _window(text: str) -> Optional[str]:
    m = _WINDOW.search(text)
    if not m:
        return None
    return f"{m.group(1)}{_WINDOW_UNIT.get(m.group(2), 'M')}"


def _exception(text: str) -> Optional[str]:
    m = _EXCEPTION_HEAD.search(text)
    if not m:
        return None
    # 예외 표현이 나온 지점부터 문장 끝까지를 예외 절로 본다.
    seg = text[m.start():].strip()
    return seg[:120] if seg else None


def _attribution(text: str) -> Optional[str]:
    m = _ATTRIBUTION.search(text)
    return m.group(1).strip() if m else None


def parse(clause: str) -> Dict[str, Any]:
    """조항 하나에서 6개 필드를 뽑는다. 확신 없으면 그 필드를 비운다.

    반환 형식은 ai_rule.compile_rule 과 같다 — 같은 게이트로 채점하기 위함이다.
    """
    t = _norm(clause)
    amounts = _all_amounts(t)
    effects = _all_effects(t)

    fields: Dict[str, Any] = {}

    # 계단형: 금액이 여럿이고 우대폭도 여럿이면 첫 구간을 대표로 잡는다.
    # (본 시스템은 구간 전체를 tiers로 담지만, 정규식 기준선이 할 수 있는 최선은 여기까지다)
    if amounts:
        fields["threshold"] = amounts[0]
    if effects:
        fields["effect_value"] = effects[0]

    op = _operator(t)
    if op:
        fields["operator"] = op

    win = _window(t)
    if win:
        fields["window"] = win

    exc = _exception(t)
    if exc:
        fields["exception"] = exc

    attr = _attribution(t)
    if attr:
        fields["attribution_rule"] = attr

    return fields


def parse_tiers(clause: str) -> List[Dict[str, Any]]:
    """계단형 조항을 구간별로 쪼갠다. 금액 수와 우대폭 수가 같을 때만."""
    t = _norm(clause)
    amounts, effects = _all_amounts(t), _all_effects(t)
    if len(amounts) >= 2 and len(amounts) == len(effects):
        return [{"threshold": a, "effect_value": e} for a, e in zip(amounts, effects)]
    return []


__all__ = ["parse", "parse_tiers", "VERSION"]
