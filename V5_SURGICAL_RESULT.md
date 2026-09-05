# Butterfin V5 — Surgical Correctness Pass 결과

작성일: 2026-09-05 (V5 패스 수행)
지시 문서: `00_READ_ME_FIRST__V5_SURGICAL_FINAL.md` (동학 업로드, V5_SURGICAL_FINAL 팩)
지시 원문: "00_READ_ME_FIRST__V5_SURGICAL_FINAL.md를 읽고 7개 blocker만 수정·검증해.
오래된 골든 데모를 보존하려고 P0를 남기지 마. 문서는 이후 최신 코드에 맞춰 다시 쓸 거야."

이 지시는 이전 세션(`CLAUDE_INDEPENDENT_AUDIT_20260905.md`)이 F02/F04를 "이미
문서화된 골든 데모 보존"을 이유로 의도적으로 남겨뒀던 판단을 명시적으로
뒤집는다. 이번 V5 패스는 그 판단을 뒤집어 7개 blocker를 전부 고쳤다.

---

## 1. Blocker별 FIXED / NOT FIXED

### BLOCKER 1 (F02) — 다중/불일치 Rule 매칭에서 matched[0] 금지 → **FIXED**

`mvp/app.py`의 이산 판정 분기(PRODUCT_TERMINATION/PAYMENT_ACCOUNT_CHANGE/
SALARY_ACCOUNT_CHANGE)에서 `len(matched) > 1`이면 `matched[0]`으로 확정하지
않고 `decision: "REVIEW"` + `candidates`(rule_id/institution/product 목록)를
반환하도록 고쳤다. 후보가 정확히 1개일 때만 자동판정한다. institution/product를
지정했는데 실제 등록된 값과 안 맞아 0건이 되는 경우는 `mvp/rule_store.py`의
"0건이면 넓은 후보로 fallback" 로직을 제거해 정직하게 0건 → REVIEW로 처리한다.

검증: `PRODUCT_TERMINATION` 단독 호출(institution/product 없음) → 3파전
(`KB_SAVINGS_LOAN_HOLD`/`HF_SUBSCRIPTION_DIDIMDOL`/`HANA_HISTORY_SAVINGS`) →
REVIEW + candidates 3건. institution/product를 주면 단일 후보로 좁혀져 여전히
자동판정됨(예: KB 조합 → HOLD).

**깨진 예전 골든 데모**: "상품 해지(기관·상품 미지정) → HOLD, 매칭
KB_SAVINGS_LOAN_HOLD" — 이제 REVIEW로 바뀐다(의도된 변경, 아래 §5 참고).

### BLOCKER 2 (F04) — Generic exception false PASS 금지 → **FIXED**

`exception_condition_met`이 `rule.get("exception")`이 실제로 존재하는(불리언
true) 규칙에만 적용되도록 게이트를 추가했다(`rule_has_real_exception = bool(rule.get("exception"))`,
`exception_met = bool(body.get(...)) and rule_has_real_exception`). exception
필드가 없는 SHINHYUP_SALARY, KB_SAVINGS_LOAN_HOLD 등은 체크값을 줘도 더 이상
면제되지 않는다.

검증: `SALARY_ACCOUNT_CHANGE` + `exception_condition_met: true` → 더 이상
PASS가 아니라 HOLD (SHINHYUP_SALARY에 exception 필드가 없으므로).
`exception_applied: false`로 정직하게 남음.

**깨진 예전 골든 데모**: "급여계좌 변경 + 아무 예외 체크 → PASS" — 폐기(README
V5 명시 지시).

### BLOCKER 3 — 새 상품 금리 비교 기능의 수학적 오류 제거 → **FIXED**

`mvp/app.py`에서 `new_product_rate_pct`/`net_effect_pct_p`/`net_effect_verdict`
계산 블록을 완전히 삭제했다. 대신 고정 disclosure 문구를 `condition.net_effect_note`로
항상 반환한다: "상품 간 원화 손익 비교는 현재금리·신규금리·원금/잔액·남은기간·
중도해지 조건 등이 필요해 현재 MVP 자동계산 범위가 아닙니다." `mvp/static/index.html`에서
"3-1. 새 상품과 비교" UI 블록과 `newProductRate` 입력 필드를 제거했다.

검증: `new_product_rate_pct` 필드를 요청에 실어 보내도 응답 `condition`에는
`new_product_rate_pct`/`net_effect_pct_p`/`net_effect_verdict` 키 자체가
존재하지 않음(무시됨). 대신 `net_effect_note` disclosure 문구가 항상 표시됨.

### BLOCKER 4 (F17) — '현재 유지 중인 우대폭' 확정 표현 수정 → **FIXED**

`index.html`의 라벨을 "현재 유지 중인 우대폭" → "규칙상 우대폭(현재 적용 여부
미확인)"으로 바꿨다. API 필드명(`condition.baseline_effect_pct_p`)은 하위
호환을 위해 유지하되, 새 `condition.baseline_effect_note` 필드("규칙상
우대폭입니다 — 현재 실제로 이 우대를 받고 있는지는 확인하지 않았습니다.")로
비확정성을 API 레벨에서도 명시하고, 화면에 note로 표시한다.

### BLOCKER 5 (F16) — HANA_HISTORY_SAVINGS 전역 PASS 금지 → **FIXED**

인과판정 자체("가입 전 확정 이력이라 지금 해지로는 안 바뀐다")는 유지하되,
`decision`을 `"PASS"`에서 `"REVIEW"`로 낮췄다. `condition.rule_status: "NOT_AFFECTED"`로
이 규칙만 영향받지 않음을 명시하고, reason을 README 지정 문구로 교체:
"이 등록 규칙은 현재 해지행동의 영향을 받지 않습니다. 해지 전체 손익은 현재
지원범위에서 검증하지 않았습니다." `index.html`도 이 case를 "예외 적용"과
구분되는 REVIEW 배지로 별도 렌더링한다.

검증: 하나은행 해지 → REVIEW, `condition.rule_status === "NOT_AFFECTED"`.

**깨진 예전 골든 데모**: "하나은행 적금 해지 → PASS" — REVIEW로 바뀐다(의도된
변경, 데모 다양성을 위한 억지 PASS 사례로 쓰지 말라는 README 지시 반영).

### BLOCKER 6 — 디딤돌 tier 0.3%p 임의 선택 금지 → **FIXED**

`HF_SUBSCRIPTION_DIDIMDOL`에 대해 (a) 공식 당첨해지 exception이 적용되지
않고, (b) `enrollment_years`/`payment_count` 같은 tier 상태값이 전혀 주어지지
않으면, `tiers[0]`을 임의로 골라 %p를 계산하지 않고 REVIEW로 "가입기간/납입회차
필요"를 안내한다. 공식 당첨해지 exception이 적용되면(`exception_condition_met`
+ 실제 exception 필드 존재) 그 경로로 안전하게 통과한다(REVIEW로 막히지 않음).

검증: 디딤돌 해지(tier 정보 없음, exception 없음) → REVIEW,
`condition.baseline_effect_pct_p is None`(임의 %p 없음). 공식 당첨해지 exception
적용 → PASS, `exception_applied: true`.

### BLOCKER 7 — KB 메인 시연의 숨은 상태값을 보이게 → **FIXED**

`CARD_SPEND_SHIFT` 응답의 `effects`에 `hist3`/`baseline_monthly` 필드를
추가했다(`{value, unit, assumed}` — `linked_balance`와 동일한 패턴). 사용자가
안 주면 대표 시나리오값(22만원×3, 22만원)을 쓰고 `assumed: true`로 명시하며,
`effects.scenario_note`로 고정 문구를 항상 반환한다: "대표 시나리오 가정: 최근
3개월 카드실적 22만원/22만원/22만원, 향후 월 22만원 (미입력 시 사용)".
`index.html`도 `linked_balance` 가정값 disclosure와 같은 자리에 hist3/baseline
가정값 note를 추가로 표시한다. (참고: README가 제시한 "더 좋은 수정"인 편집
가능한 입력 UI는 이번 패스 범위(최소 수정)에서는 구현하지 않았다 — 최소 수정
요건인 "표시"는 충족했다.)

---

## 2. 변경 파일

- `mvp/rule_store.py` — `match()`에서 institution/product 좁히기 실패 시
  넓은 후보로 되돌아가던 fallback 제거 (BLOCKER 1의 기반).
- `mvp/app.py` — 이산 판정 분기 전면 수정: 다중매치 REVIEW 가드(BLOCKER 1),
  exception 게이팅(BLOCKER 2), 새 상품 비교 기능 제거(BLOCKER 3), 우대폭
  wording/disclosure 추가(BLOCKER 4), HANA PASS→REVIEW(BLOCKER 5), 디딤돌
  tier REVIEW 게이트(BLOCKER 6), hist3/baseline disclosure(BLOCKER 7).
- `mvp/static/index.html` — 새 상품 비교 입력/렌더 블록 제거, "규칙상
  우대폭(현재 적용 여부 미확인)" wording, NOT_AFFECTED/review_note 케이스
  전용 렌더링, 다중후보 REVIEW 전용 렌더링(candidates 목록), hist3/baseline
  가정값 note 추가.
- `tests/test_action_interpreter.py` — 존재하지 않는 product → 0건 반환
  검증으로 수정(구 fallback 기대값 → 신규 fail-closed 기대값).
- `tests/test_fix4_safezone.py` — 이산 판정 테스트에 institution/product
  명시 추가(다중매치 REVIEW 회피), 새 상품 비교 기능(F14) 테스트 블록 전체
  삭제 및 필드 부재/disclosure 검증으로 교체.
- `tests/test_safezone_v12.py` — 테스트 #16을 PAYMENT_ACCOUNT_CHANGE +
  KBANK_TELECOM_SAVINGS(실제 exception 필드 보유)로 교체(KB_SAVINGS_LOAN_HOLD는
  BLOCKER 2로 인해 더 이상 exception 체크만으로 면제되지 않으므로).
- `tests/test_independent_audit_20260905.py` — 헤더 재작성, 7개 blocker 전체를
  회귀 테스트로 고정(다중매치 REVIEW, exception 게이팅, HANA REVIEW, 디딤돌
  tier REVIEW/exception 통과, 새 상품 비교 필드 부재, hist3/baseline
  disclosure).
- `V5_SURGICAL_RESULT.md` — 본 문서(신규).

---

## 3. 테스트 결과

```
tests/test_action_interpreter.py         23 passed, 0 failed
tests/test_ai_rule.py                    23 passed, 0 failed
tests/test_ai_rule_openai_provider.py    22 passed, 0 failed
tests/test_baseline_regex.py             30 passed, 0 failed
tests/test_dev25_runner.py               12 passed, 0 failed
tests/test_engine.py                     22 passed, 0 failed
tests/test_fix4_safezone.py              31 passed, 0 failed
tests/test_independent_audit_20260905.py 26 passed, 0 failed
tests/test_openai_provider.py             9 passed, 0 failed
tests/test_safezone_v12.py               26 passed, 0 failed
--------------------------------------------------------------
합계                                     224 passed, 0 failed
```

README V5의 "검증 필수" 13개 항목 실측 결과:

1. 존재하지 않는 institution/product → REVIEW: **확인** (`decision: REVIEW`, 매칭 규칙 없음)
2. PRODUCT_TERMINATION 상품 미지정 + 후보 다수 → REVIEW: **확인** (3건 후보, candidates 반환)
3. SALARY_ACCOUNT_CHANGE + generic exception=true → PASS가 나오지 않음: **확인** (HOLD, exception_applied: false)
4. Didimdol 공식 exception → rule-specific 처리: **확인** (PASS, exception_applied: true, 원 exception 텍스트 그대로 반환)
5. Didimdol tier state 없음 → 0.3%p 임의 출력 없음: **확인** (REVIEW, baseline_effect_pct_p: null)
6. HANA termination → 전역 PASS 오해 없음: **확인** (REVIEW, rule_status: NOT_AFFECTED)
7. new_product_rate 입력 → 잘못된 +X%p 경제효과 계산 없음: **확인** (필드 자체가 응답에서 사라짐)
8. KB 50,000 HOLD 유지: **확인** (동일 D/L/G/2개월 TTR)
9. KB 20,000 PASS 유지: **확인**
10. KB Safe Zone 가정값이 UI에 보임: **확인** (effects.hist3/baseline_monthly + scenario_note, index.html note)
11. 기존 보안/타입 테스트 유지: **확인** (F23/F27 테스트 26개 모두 통과)
12. 실제 OpenAI 경로 smoke: **미실시** — 이 샌드박스에 실 API 키가 없어 실행 불가(기존 세션부터 동일 제약, mock 경로로만 검증)
13. 모바일/Chrome smoke: **미실시** — 이 샌드박스는 브라우저 렌더링 환경이 없어 정적 코드 검증(index.html 문자열/구조 확인)으로 대체함

---

## 4. 최종 Golden Demo 3개 (README "Golden Demo 최종 재구성" 반영)

### Demo 1 — 킬러 (KB 카드실적)
```
입력: action_type=CARD_SPEND_SHIFT, institution=KB국민은행,
      product=대출 금리감면 (일반 신용대출), amount_monthly=50000,
      direct_benefit_monthly=1000
→ decision: HOLD
→ effects.hist3: {value:[220000,220000,220000], assumed:true}
   effects.baseline_monthly: {value:220000, assumed:true}
   scenario_note: "대표 시나리오 가정: 최근 3개월 카드실적 22만원/22만원/22만원, 향후 월 22만원 (미입력 시 사용)"
→ D/L/G: 2개월 시점 기준 계산됨 (TTR=2)
→ safety.robust_safe_zone: 0~20,000원

조정 후: amount_monthly=20000 → decision: PASS (12개월 내 위반 없음)
```

### Demo 2 — 공식 exception / 비금액 규칙 (디딤돌 청약)
```
입력 A (tier 정보 없음): action_type=PRODUCT_TERMINATION,
      institution=주택금융공사, product=내집마련 디딤돌대출
→ decision: REVIEW, reason: "가입기간·납입회차에 따라 우대폭이 달라지는
   구간형 규칙입니다. ... 가입기간/납입회차 정보가 없어 정확한 상실
   우대폭(%p)을 특정할 수 없습니다."
→ condition.baseline_effect_pct_p: null (tiers[0] 임의 선택 없음)

입력 B (공식 당첨해지 exception): 위와 동일 + exception_condition_met=true
→ decision: PASS, reason: "예외 조항이 적용됩니다: 본 건 목적물 당첨에
   따라 해지된 계좌는 해지 여부 확인 대상에서 제외"
→ condition.exception_applied: true
```

### Demo 3 — Fail-closed (상품 미지정/잘못된 조합)
```
입력 A (상품 미지정, 3파전): action_type=PRODUCT_TERMINATION
→ decision: REVIEW, matched_rules: [KB_SAVINGS_LOAN_HOLD,
   HF_SUBSCRIPTION_DIDIMDOL, HANA_HISTORY_SAVINGS]
→ candidates: 3건 (각 rule_id/institution/product) — "은행/상품명을
   함께 알려주세요"

입력 B (등록되지 않은 상품명): action_type=CARD_SPEND_SHIFT,
      product=존재하지않는상품명
→ decision: REVIEW, matched_rules: [] — "이 행동과 연결된 Verified/Fresh
   Rule을 찾지 못했습니다."
```

이 3개로 계산능력(Demo 1)·rule-native 조건/공식근거(Demo 2)·안전한 AI
(Demo 3, 임의 확정 판정 금지)를 모두 보여준다.

---

## 5. 문서에서 바꿔야 할 문장 (제출 스펙/발표자료 대상)

기존 배포본_재검증기록.md 등에 이미 박혀 있던 아래 문장들은 이번 V5 코드
변경으로 실제 동작과 어긋나게 됐다 — 새 코드에 맞춰 다시 써야 한다.

1. "상품 해지(기관·상품 미지정) → HOLD, 매칭 KB_SAVINGS_LOAN_HOLD"
   → "상품 해지(기관·상품 미지정) → REVIEW(후보 3건 중 특정 요청)". 확정
   판정이 필요하면 기관/상품을 반드시 함께 입력해야 한다는 점을 명시.
2. "급여계좌 변경 + 아무 예외 체크 → PASS"
   → 이 시나리오는 폐기. "SHINHYUP_SALARY는 공식 예외 조항이 없는 규칙이라
   체크박스가 면제를 주지 않는다"로 대체.
3. "하나은행 적금 해지 → PASS"
   → "하나은행 적금 해지 → REVIEW(해당 규칙은 영향받지 않으나 해지 전체
   손익은 별도 확인 필요)"로 대체.
4. "현재 유지 중인 우대폭 X%p" 같은 확정형 표현이 등장하는 모든 문장
   → "규칙상 우대폭(현재 적용 여부 미확인) X%p"로 대체.
5. "새 상품 금리와 비교해 순 효과 계산" 관련 문장/스크린샷
   → 기능 자체가 제거됐으므로 삭제. 대신 "상품 간 손익 비교는 이번 MVP
   범위 밖"이라는 disclosure 문구로 대체.
6. Safe Zone/TTB/TTR 설명에 "최근 3개월 카드실적/향후 실적을 어떻게
   가정했는지" 언급이 없었다면, hist3/baseline 대표 시나리오 가정값(22만원)을
   명시하는 문장을 추가.

---

## 6. 최종 판정: **GO**

7개 blocker 전부 FIXED. 금융적으로 잘못된 PASS(SHINHYUP_SALARY generic
exception, HANA 전역 PASS)나 잘못된 숫자(디딤돌 tiers[0] 임의 %p, 새 상품
금리 차원 불일치 비교)를 만드는 경로가 더 이상 남아있지 않다. KB 킬러 데모
(50,000원 → HOLD, D/L/G·Safe Zone 정상 계산 / 20,000원 → PASS)는 그대로
재현된다. 전체 224개 테스트가 통과하고, README가 요구한 13개 검증 필수
항목 중 이 샌드박스에서 실행 가능한 11개를 전부 실측 확인했다(12/13은
실제 OpenAI 키·브라우저 환경이 이 샌드박스에 없어 미실시 — 기존 세션부터
동일한 환경 제약).

GO 조건("위 1~7 중 금융적으로 잘못된 PASS/잘못된 숫자를 만드는 blocker가
남아 있지 않고, KB 킬러 데모가 그대로 재현되면 GO")을 충족한다.

깨진 예전 골든 데모 3건(§1의 BLOCKER 1/5, §5의 문장 1/3)은 의도된 변경이며,
동학의 명시적 지시("오래된 골든 데모를 보존하려고 P0를 남기지 마")에 따라
방치하지 않고 고쳤다. 제출 문서는 §5의 문장들을 새 코드 동작에 맞춰 다시
써야 한다.
