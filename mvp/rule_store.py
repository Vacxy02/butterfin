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

    def match(self, action_type: str, institution: Optional[str] = None,
              product: Optional[str] = None) -> List[Dict[str, Any]]:
        """action_type(CARD_SPEND_SHIFT 등)에 해당하는 규칙을 전부 반환한다.

        institution과 product는 각각 독립적으로 좁힌다 — 은행명 하나만으로는 상품을
        특정할 수 없다(예: 한 은행이 여러 상품을 취급하거나, 같은 상품을 여러 은행이
        취급할 수 있음). 둘 다 주면 두 조건을 순서대로 다 적용해서 더 좁힌다.

        2026-09-05 (V7 FIX 1, strict/fail-closed matching): 예전엔 institution/
        product로 좁힌 결과가 0건이면 그 필터를 무시하고 더 넓은 후보군으로 조용히
        되돌아갔다 — 그 결과 사용자가 존재하지 않는(또는 오타난) 기관/상품명을
        지정해도 엉뚱한 규칙이 매칭돼 confident한 PASS/HOLD를 낼 수 있는 위험한
        fallback이었다. 이제는 사용자가 institution/product를 명시했는데 그 값이
        실제 등록된 어느 규칙과도 안 맞으면 정직하게 0건을 반환한다 — 호출부
        (app.py)가 이를 REVIEW로 안전하게 처리한다. institution/product를 아예
        안 준 경우는 원래부터 그 축을 좁히지 않으므로 영향 없다."""
        candidates = [r for r in self.rules if action_type in r.get("action_types", [])]
        if institution:
            candidates = [r for r in candidates if institution in r.get("institution", "")]
        if product:
            candidates = [r for r in candidates if product in r.get("product", "")]
        return candidates

    def all_fresh(self, rule_ids: List[str]) -> bool:
        for rid in rule_ids:
            r = self.get(rid)
            if r is None or r.get("freshness") != "FRESH":
                return False
        return True

    def known_institutions(self) -> List[str]:
        """지금 실제로 등록된 규칙들의 institution 값 목록(중복 제거, 등장 순서 유지).
        action_interpreter.py의 은행명 감지, index.html의 상품 선택 드롭다운이
        demo_rules.json이 바뀔 때마다 따로 손보지 않아도 항상 최신으로 맞게 이걸로
        가져다 쓴다 — 값을 여기저기 하드코딩해서 나중에 어긋나는 걸 막기 위함."""
        seen: List[str] = []
        for r in self.rules:
            inst = r.get("institution")
            if inst and inst not in seen:
                seen.append(inst)
        return seen

    def known_products(self) -> List[str]:
        """지금 실제로 등록된 규칙들의 product 값 목록(중복 제거, 등장 순서 유지).
        institution과 마찬가지로 상품명 감지/드롭다운이 이걸 단일 출처로 쓴다."""
        seen: List[str] = []
        for r in self.rules:
            prod = r.get("product")
            if prod and prod not in seen:
                seen.append(prod)
        return seen


if __name__ == "__main__":
    store = RuleStore()
    print(f"규칙 {len(store.rules)}개 로딩 확인")
    for r in store.rules:
        print(f"  - {r['rule_id']} ({r['institution']} · {r['freshness']})")
