"""
Verified/Fresh Rule 저장소. demo_rules.json(사람이 검수 승인한 규칙)만 로드한다.
Rule Compiler가 만든 candidate rule은 여기 자동으로 들어오지 않는다 — 사람이
승인(approve)해야 이 파일에 추가된다 (이번 세션 범위에서는 승인 CLI는 만들지 않고,
사람이 demo_rules.json을 직접 편집하는 것으로 대체한다).
"""

from __future__ import annotations

import json
import os
from typing import List, Dict, Any, Optional

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "demo_rules.json")


class RuleStore:
    def __init__(self, path: str = _DEFAULT_PATH):
        self.path = path
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def reload(self) -> None:
        self._data = self._load()

    @property
    def rules(self) -> List[Dict[str, Any]]:
        return self._data.get("rules", [])

    def get(self, rule_id: str) -> Optional[Dict[str, Any]]:
        for r in self.rules:
            if r["rule_id"] == rule_id:
                return r
        return None

    def match(self, action_type: str, institution: Optional[str] = None) -> List[Dict[str, Any]]:
        """action_type(CARD_SPEND_SHIFT 등)에 해당하는 규칙을 전부 반환한다.
        institution이 주어지면 그 기관 규칙을 우선하되, 없으면 전체 매칭을 반환한다
        (사용자가 어느 상품인지 모를 수 있으므로 REVIEW로 넘겨 사람이 고르게 한다)."""
        candidates = [r for r in self.rules if action_type in r.get("action_types", [])]
        if institution:
            narrowed = [r for r in candidates if institution in r.get("institution", "")]
            if narrowed:
                return narrowed
        return candidates

    def all_fresh(self, rule_ids: List[str]) -> bool:
        for rid in rule_ids:
            r = self.get(rid)
            if r is None or r.get("freshness") != "FRESH":
                return False
        return True


if __name__ == "__main__":
    store = RuleStore()
    print(f"규칙 {len(store.rules)}개 로딩 확인")
    for r in store.rules:
        print(f"  - {r['rule_id']} ({r['institution']} · {r['freshness']})")
