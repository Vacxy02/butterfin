# V7_DOC_UPDATE_FACTS.md — 문서 재작성 시 참고할 최신 코드 사실

`COPY_PASTE_PROMPT.txt`의 마지막 문장("이후 문서는 최신 코드에 맞춰 다시 쓸
거야")을 위해, 문서를 다시 쓸 때 근거로 삼아야 할 "지금 코드가 실제로 하는 일"만
사실 위주로 정리한다. 해석이나 평가는 넣지 않았다.

## 규칙 매칭 (`mvp/rule_store.py`, `mvp/app.py`)

- `RuleStore.match(action_type, institution=None, product=None)`은 institution/
  product로 좁힌 결과가 0건이면 **정직하게 0건을 반환**한다(넓은 후보로 되돌아가는
  fallback 없음).
- `/api/evaluate`는 매칭 0건이면 REVIEW.
- `action_type != "CARD_SPEND_SHIFT"`이고 매칭이 2건 이상이면 `matched[0]`을 쓰지
  않고 REVIEW + `candidates`(rule_id/institution/product 목록)를 반환한다.
- CARD_SPEND_SHIFT는 이 게이트 대상이 아니다 — `compute_safe_zone`이 `tiers`와
  `min_won`이 있는 모든 매칭 규칙(`qualifying_rules`)을 함께 계산해 가장 엄격한
  계약을 `binding_constraints`로 명시한다.

## 예외(exception) 처리

- `exception_condition_met`은 사용자가 보낸 boolean 그대로 서버가 받되, 매칭된
  규칙(`matched[0]`, 이산형)에 `exception` 필드가 없으면 무시된다
  (`rule_has_real_exception = bool(rule.get("exception"))`).
- 현재 8개 규칙 중 실제 `exception` 필드가 있는 건 `HF_SUBSCRIPTION_DIDIMDOL`,
  `KBANK_TELECOM_SAVINGS` 둘뿐이다.

## 디딤돌대출(`HF_SUBSCRIPTION_DIDIMDOL`) 특수 처리

- 공식 예외(`exception_condition_met=True`)가 적용되지 않고, `enrollment_years`도
  `payment_count`도 안 주면 → REVIEW, `condition.review_note`에 이유 설명. `tiers[0]`
  임의 선택 없음.
- 둘 중 하나라도 주면(향후 구간 결정 로직 확장 여지가 있다는 뜻 — 이번 V7 범위에서는
  "REVIEW로 남긴다"까지만 구현, 실제 구간별 %p 계산 로직 자체는 이번에 새로 만들지
  않았다) 또는 공식 예외가 적용되면 판정이 내려진다.

## HANA_HISTORY_SAVINGS

- 결정은 항상 **PASS**다(V5 초안에서 REVIEW로 낮췄던 것과 다름 — 최종 채택은
  PASS 유지).
- reason: "이 등록 규칙(가입 전 6개월 이력)은 현재 해지행동의 영향을 받지 않습니다.
  해지 전체 손익을 의미하지 않습니다."
- `condition.causal_note`: "가입 전 이력 조건 — 현재 행동으로는 훼손 불가"

## 이산형 응답의 D/L/G/reversal

- PRODUCT_TERMINATION/PAYMENT_ACCOUNT_CHANGE/SALARY_ACCOUNT_CHANGE 판정에서
  `effects.D`, `effects.L`, `effects.G`는 항상 `null`이다.
- `effects.reversal`과 최상위 `action_reversal`은 이산형에서 **항상 `false`**다 —
  `discrete.violation`(위반 여부)과 무관하다. 위반 여부는 `decision`(PASS/HOLD)과
  `condition.lost_pct_p`/`condition.exception_applied`로 표현된다.

## 퍼센트 입력창(`new_product_rate_pct`)

- 입력창(화면 id `newProductRate`)은 그대로 있다.
- 서버는 입력값을 그대로 `condition.new_product_rate_pct`로 에코하고,
  `condition.new_product_rate_note`(고정 문구: "두 값은 서로 다른 금융계약의
  지표이므로 단순 차감하지 않습니다. 실제 원화 손익 비교에는 원금/잔액,
  현재·신규금리, 남은 기간, 중도해지 조건 등이 추가로 필요합니다.")를 함께
  내려준다.
- `net_effect_pct_p`/`net_effect_verdict`/ADVANTAGEOUS·DISADVANTAGEOUS·EQUAL
  배지는 응답에서 완전히 사라졌다.

## 시나리오 가정 (hist3 / baseline_monthly)

- CARD_SPEND_SHIFT 계산에 쓰는 기본값: `hist3=[220000, 220000, 220000]`,
  `baseline_monthly=220000`.
- 사용자가 안 주면 이 기본값을 쓰고, 응답의 `effects.hist3.assumed`/
  `effects.baseline_monthly.assumed`가 `true`로 찍힌다. `effects.scenario_note`에
  설명 문구가 함께 온다.

## 공통 고지 (SCOPE_NOTE)

- 모든 `/api/evaluate` 응답(REVIEW/PASS/HOLD/EXECUTION_BLOCKED 전부)에
  `scope_note` 필드가 붙는다: "본 판정은 아래에 매칭된 등록 규칙과 입력/시나리오
  범위 기준입니다."

## 화면(index.html) 표시 규칙

- `data.effects`가 없는 응답(규칙 불일치/다중매칭 REVIEW 등)은 상세 섹션을
  렌더링하지 않고 후보 목록 + 매칭 규칙 + scope_note만 보여준다.
- 이산형 결과는 "10. Action Reversal" 대신 "10. 조건 유지/위반"을 보여준다.
  CARD_SPEND_SHIFT는 그대로 "10. Action Reversal"을 보여준다.
- "3. [행동] — 조건 유지 현황"의 우대폭 라벨은 "이 등록 규칙상 우대폭"으로
  표기한다("현재 유지 중인 우대폭"에서 변경).
