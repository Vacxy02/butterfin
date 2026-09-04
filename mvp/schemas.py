"""
공통 데이터 스키마.
- TypedActionDelta: 사용자 자연어 행동 → 구조화된 상태 변화 (action_interpreter.py 출력,
  app.py의 /api/interpret·/api/evaluate가 그대로 씀).

(2026-08-25: 예전에는 여기 CandidateRule(16필드)/Tier/VerifiedRule도 있었는데, 팀의 실제
ai_rule.py/blind25_fixed.py가 도착하면서 그 역할은 blind25_fixed.ExtendedRuleSchema(14필드,
pydantic)로 넘어갔고 엔진/규칙저장소는 engine.py·rule_store.py가 자체 표현을 쓴다 —
아무 데서도 안 쓰던 죽은 코드라 정리 차원에서 뺐다.)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

# ---------------------------------------------------------------------------
# Typed Action Delta — 자연어 행동 해석 결과
# (PROJECT_CURRENT_STATE.md §8 최소 행동 유형)
# ---------------------------------------------------------------------------

ACTION_TYPES = [
    "CARD_SPEND_SHIFT",
    "SALARY_ACCOUNT_CHANGE",
    "PAYMENT_ACCOUNT_CHANGE",
    "PRODUCT_TERMINATION",
]


@dataclass
class TypedActionDelta:
    status: str  # OK | NEED_INFO | UNSUPPORTED | ERROR
    action_type: Optional[str] = None
    target_metric: Optional[str] = None  # 예: rolling_3m_card_spend
    amount_monthly: Optional[float] = None
    raw_text: Optional[str] = None
    clarifying_question: Optional[str] = None
    reason: Optional[str] = None
    # 2026-08-28 추가: 문장에 특정 은행/상품명이 언급됐으면 그 기관명(rule_store의
    # demo_rules.json institution 필드와 정확히 같은 문자열)을 담는다. AI가 자유롭게
    # 추출한 값이 아니라 action_interpreter._detect_institution()이 "실제로 등록된
    # 기관 목록"과 대조해서 채운 값이다 — 없는 은행 이름을 지어내지 않는다.
    institution: Optional[str] = None
    # 은행명만으로는 상품을 특정할 수 없다(한 은행이 여러 상품을 취급하거나, 같은
    # 상품을 여러 은행이 취급할 수 있음) — 그래서 상품명도 institution과 똑같은
    # 방식(_detect_product(), 실제 등록된 product 목록과 대조)으로 독립적으로 채운다.
    product: Optional[str] = None
    # 2026-09-04 추가: 문장에 "이 행동으로 즉시 얻는 이득(캐시백 등)"이 금액과 함께
    # 명시돼 있으면 그 값을 담는다. amount_monthly(행동 자체의 금액)와는 완전히 다른
    # 개념이라 별도 필드로 분리한다 — action_interpreter.SYSTEM_PROMPT가 이 둘을
    # 구분해서 뽑도록 지시한다. 문장에 없으면 None이며, 화면(카드 2)은 이 값이 None이면
    # 기존처럼 0을 기본값으로 두고 사용자가 직접 입력하게 한다(추측해서 채우지 않음).
    direct_benefit_monthly: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
