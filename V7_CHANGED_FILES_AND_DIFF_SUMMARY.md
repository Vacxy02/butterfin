# V7_CHANGED_FILES_AND_DIFF_SUMMARY.md

이번 V7 패스에서 실제로 수정/추가한 파일 전체 목록과 각 파일에서 무엇이 바뀌었는지
요약. 나머지 모든 파일(engine.py, action_interpreter.py, schemas.py,
openai_client.py, demo_rules.json 등)은 **이번 V7 범위에서 한 글자도 바꾸지
않았다**.

## 수정한 파일

### `mvp/rule_store.py`
- `match()`에서 institution/product로 좁힌 결과가 0건일 때 더 넓은 후보로
  되돌아가던 fallback 로직을 제거. 이제 0건이면 그대로 0건을 반환한다.
  (FIX 1)

### `mvp/app.py`
- `SCOPE_NOTE` 상수 추가, 모든 `/api/evaluate` 응답에 실어 보냄. (FIX 7)
- `matched = store.match(...)` 이후 `action_type != "CARD_SPEND_SHIFT"`이고
  `len(matched) > 1`이면 REVIEW + `candidates` 반환하는 게이트 추가. (FIX 1)
- 이산형 분기에서 `rule_has_real_exception`/`exception_met` 게이팅 추가 —
  규칙에 `exception` 필드가 실제로 있을 때만 `exception_condition_met`을
  반영. (FIX 2)
- `HF_SUBSCRIPTION_DIDIMDOL` 전용 REVIEW 블록 추가 — 가입기간/납입회차 정보
  없이는 tiers[0]을 임의 선택하지 않고 REVIEW + `review_note` 반환. (FIX 3)
- 이산형 최종 응답에서 `effects.reversal`/`action_reversal`을 `discrete.violation`
  대신 항상 `False`로 고정. (FIX 4)
- `net_effect_pct_p`/`net_effect_verdict` 계산 블록 삭제, 대신
  `new_product_rate_pct` 그대로 에코 + `new_product_rate_note` 고정 문구
  추가. (FIX 5)
- CARD_SPEND_SHIFT 분기에 `hist3`/`baseline_monthly` assumed 추적 추가,
  응답의 `effects.hist3`/`effects.baseline_monthly`/`effects.scenario_note`로
  노출. (FIX 6)
- `HANA_HISTORY_SAVINGS` 응답의 reason 문구 갱신(결정은 PASS로 불변). (FIX 7)

### `mvp/static/index.html`
- `data.effects`가 없는 응답(규칙 불일치/다중매칭 REVIEW)을 위한 방어 렌더링
  추가 — 후보 목록 카드 + 매칭 규칙 + scope_note만 표시하고 나머지 상세
  섹션은 렌더링하지 않음.
- "3. [행동] — 조건 유지 현황"의 라벨을 "현재 유지 중인 우대폭" → "이 등록
  규칙상 우대폭"으로 변경. (FIX 7)
- "3-1. 새 상품과 비교" 블록에서 net_effect 기반 배지 렌더링을 제거하고
  `new_product_rate_note` 표시로 교체. (FIX 5)
- 디딤돌대출류 REVIEW 응답의 `condition.review_note`를 화면에 표시하는 블록
  추가. (FIX 3)
- CARD_SPEND_SHIFT 결과에 hist3/baseline 가정값 고지 문구 추가. (FIX 6)
- 결과 화면 하단에 `scope_note` 공통 고지 표시 추가. (FIX 7)
- (이번 V7 패스 이전, 별도 요청으로 이미 적용됨: 이산형은 "10. Action
  Reversal" 대신 "10. 조건 유지/위반" 섹션을 보여줌 — 그대로 유지, 추가 변경
  없음)

## 갱신한 기존 테스트

- `tests/test_action_interpreter.py`
- `tests/test_fix4_safezone.py`
- `tests/test_safezone_v12.py`
- `tests/test_independent_audit_20260905.py`

(각 파일에서 정확히 무엇을 바꿨는지는 `V7_TEST_REPORT.md`의 "갱신한 기존 테스트"
절 참조)

## 신규 추가 파일

- `tests/test_v7_hardening.py` — `02_FINAL_TEST_AND_FREEZE.md` §A 13개 항목
  회귀 테스트(20건)
- `V7_FINAL_RESULT.md`, `V7_TEST_REPORT.md`, `V7_LIVE_SMOKE.md`,
  `V7_FINAL_DEMO_SCRIPT.md`, `V7_DOC_UPDATE_FACTS.md`,
  `V7_REMAINING_LIMITATIONS.md`, `V7_CHANGED_FILES_AND_DIFF_SUMMARY.md`(이 파일
  자신), `FILE_MANIFEST_SHA256.txt`

## 손대지 않은 파일 (명시적으로 확인)

`mvp/engine.py`, `mvp/action_interpreter.py`, `mvp/schemas.py`,
`mvp/openai_client.py`, `mvp/demo_rules.json`, `tests/test_ai_rule.py`,
`tests/test_ai_rule_openai_provider.py`, `tests/test_baseline_regex.py`,
`tests/test_dev25_runner.py`, `tests/test_engine.py`,
`tests/test_openai_provider.py` — 전부 이전 세션 상태 그대로.
