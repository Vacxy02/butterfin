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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
