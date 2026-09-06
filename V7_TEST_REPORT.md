# V7_TEST_REPORT.md

`for f in tests/test_*.py; do python3 "$f"; done` 실행 결과(2026-09-06, 이 세션에서
직접 실행/기록, 가짜 숫자 없음).

| 파일 | 결과 |
|---|---|
| tests/test_action_interpreter.py | 23 passed, 0 failed |
| tests/test_ai_rule.py | 23 passed, 0 failed |
| tests/test_ai_rule_openai_provider.py | 22 passed, 0 failed |
| tests/test_baseline_regex.py | 30 passed, 0 failed |
| tests/test_dev25_runner.py | 12 passed, 0 failed |
| tests/test_engine.py | 22 passed, 0 failed |
| tests/test_fix4_safezone.py | 36 passed, 0 failed |
| tests/test_independent_audit_20260905.py | 19 passed, 0 failed |
| tests/test_openai_provider.py | 9 passed, 0 failed |
| tests/test_safezone_v12.py | 26 passed, 0 failed |
| tests/test_v7_hardening.py (신규) | 20 passed, 0 failed |
| **합계** | **242 passed, 0 failed** |

## 이번 V7 패스에서 갱신한 기존 테스트(§C: "잘못된 동작을 정답으로 고정한 테스트"
정리)

- `test_action_interpreter.py`: 존재하지 않는 product로 `rule_store.match()`를
  호출하면 예전엔 fallback으로 0건이 아니었는데, 이제는 정직하게 0건을 반환하는 걸
  검증하도록 갱신.
- `test_fix4_safezone.py`: (1) discrete 케이스 호출에 institution/product를 추가해
  새로 생긴 다중매칭 REVIEW 게이트에 걸리지 않게 함. (2) "3-1. 새 상품과 비교" 관련
  검증 블록 전체를 net_effect_pct_p/net_effect_verdict 검증에서 → 퍼센트 입력값
  에코 + new_product_rate_note 검증으로 재작성.
- `test_safezone_v12.py`: 테스트 16번을 애매한 PRODUCT_TERMINATION 대신 실제
  exception 필드가 있는 KBANK_TELECOM_SAVINGS(PAYMENT_ACCOUNT_CHANGE)로 바꾸고,
  `effects.reversal`이 위반 여부와 무관하게 항상 `False`임을 검증하도록 갱신(위반
  여부는 `decision`으로 확인).
- `test_independent_audit_20260905.py`: 4개 항목 갱신 — (1) SHINHYUP_SALARY에
  `exception_condition_met=True`를 줘도 더 이상 PASS가 아님(HOLD 유지, exception
  필드 없음). (2) institution/product 없는 PRODUCT_TERMINATION은 이제 3건 중복
  매칭이라 REVIEW(새 KB-특정 호출을 추가해 기존 HOLD 검증은 그쪽으로 이동). (3)
  HANA_HISTORY_SAVINGS reason 문구 갱신에 맞춰 substring 검증 갱신(결정 자체는
  PASS로 불변). (4) "다른 규칙에는 영향 없음" 검증을 KB-특정 단일 매칭 호출 기준으로
  수정.

## 신규 회귀 테스트: `test_v7_hardening.py`

`02_FINAL_TEST_AND_FREEZE.md` §A의 13개 필수 항목을 항목 번호까지 맞춰 1:1로
구현했다(항목 1~13, 20개 개별 assertion). 모두 이번 세션에서 직접 실행해 통과를
확인했다 — 문서만 쓰고 실행 안 한 항목 없음.

## Golden Demo 재검증 (§B)

이 세션에서 직접 `flask.test_client()`로 실행해 확인:

- **Demo 1 (killer)**: KB국민은행/대출 금리감면, 5만원/월 → `decision=HOLD`,
  `effects.D=2000`, `effects.G=-6333`, `action_reversal=True`. 같은 조건에서 2만원/월
  → `decision=PASS`. (D>0·G<0 실제 계산 → HOLD, 임계값 아래로 낮추면 PASS — 기존
  메인 시연과 동일하게 보존됨)
- **Demo 2 (rule-native / official exception)**: HF_SUBSCRIPTION_DIDIMDOL,
  `exception_condition_met=True` → `decision=PASS`("예외 조항이 적용됩니다...").
  같은 규칙에 `exception_condition_met=False`이고 `enrollment_years`/
  `payment_count` 둘 다 없으면 → `decision=REVIEW`(FIX 3, tiers[0] 임의 확정 금지).
- **Demo 3 (fail-closed)**: PRODUCT_TERMINATION을 institution/product 없이 보내면
  3개 규칙(KB_SAVINGS_LOAN_HOLD/HF_SUBSCRIPTION_DIDIMDOL/HANA_HISTORY_SAVINGS)이
  동시에 매칭 → `decision=REVIEW`(FIX 1, 임의 선택 금지).

## 정직하게 밝히는 한계

- 이 리포트의 모든 결과는 로컬 Flask 테스트 클라이언트(`flask.test_client()`) 기준이다.
  실제 브라우저(Chrome/모바일)에서의 렌더링, 실제 배포된 `https://butterfin.onrender.com`
  에서의 동작은 이 환경에서 직접 확인할 수 없다 — `V7_LIVE_SMOKE.md`에 어디까지
  검증했고 어디부터 동학님이 직접 확인해야 하는지 구분해뒀다.
- 실제 OpenAI 키를 쓰는 라이브 AI 해석 경로는 이 환경에 키가 없어 mock/에러-주입
  테스트로만 검증했다(F27 관련 기존 테스트가 이 부분을 커버).
