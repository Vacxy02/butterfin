# V7_FINAL_RESULT.md — Butterfin V7 CODE FREEZE

- 작업 기준일: 2026-09-06
- 대상: `Butterfin V7 — SINGLE HANDOFF PACK`의 `COPY_PASTE_PROMPT.txt` 지시 전체
- 결과: **7개 FIX 전부 적용, 테스트 전체 통과(242/242), CODE FREEZE**

## 한 줄 요약

`01_FINAL_7_FIXES.md`가 지정한 7개 항목만 정확히 고쳤다. Safe Zone 전면확장, N-D/Joint
Action, 새 입력 UI, 새 추천 기능 등 "절대 하지 말 것" 목록에 있는 어떤 것도 건드리지
않았다. 퍼센트 입력창(`newProductRate`)은 그대로 유지했고, 그 값을 이용해 판정을
지어내던 로직(net_effect_pct_p/net_effect_verdict)만 제거했다.

## 적용한 7개 FIX

1. **Strict/fail-closed 규칙 매칭** — `rule_store.match()`가 institution/product로
   좁힌 결과가 0건이면 더 넓은 후보로 조용히 되돌아가던 fallback을 제거했다. 존재하지
   않는(또는 오타난) 기관/상품명을 주면 이제 정직하게 0건을 반환하고, `app.py`는 이를
   REVIEW로 처리한다. 추가로, institution/product가 충분히 안 좁혀져 이산형(해지/
   계좌변경) 규칙이 2개 이상 매칭되면 `matched[0]`을 임의로 골라 확정 판정하던 것을
   멈추고 "영향받는 보유계약을 특정해주세요"라는 REVIEW + 후보 목록으로 응답한다.
   CARD_SPEND_SHIFT는 이 게이트에서 제외했다 — `compute_safe_zone`이 이미 다중계약을
   전부 반영해 계산하는 구조라 임의 선택 문제 자체가 없기 때문이다.
2. **예외(exception) 게이팅** — `exception_condition_met=True`를 사용자가 보내도,
   매칭된 규칙 자체에 `exception` 필드가 없으면(SHINHYUP_SALARY, SHINHYUP_CARD_ACCOUNT,
   HANA_HISTORY_SAVINGS, KB_SAVINGS_LOAN_HOLD 등) 더 이상 예외를 적용하지 않는다.
   실제 `exception` 필드가 있는 규칙(HF_SUBSCRIPTION_DIDIMDOL, KBANK_TELECOM_SAVINGS)
   에만 적용된다.
3. **디딤돌대출 구간(tier) fail-closed** — `enrollment_years`/`payment_count` 둘 다
   없고 공식 예외도 적용되지 않으면, 예전처럼 `tiers[0]`(0.3%p)을 임의로 골라 확정
   판정을 내리지 않는다. 대신 REVIEW로 남기고, `condition.review_note`에 왜
   REVIEW인지와 사용자가 다음에 뭘 입력하면 되는지를 설명한다.
4. **이산형 Action Reversal 억제** — `effects.reversal`/`action_reversal`은 이산
   판정(해지/결제계좌 변경/급여계좌 변경)에서 항상 `False`다(`discrete.violation`
   여부와 무관). D/G를 계산하지 않는 유형에 "Action Reversal 예/아니오"를 보여주는
   건 계산하지 않은 걸 계산한 것처럼 보이게 하는 위험이 있기 때문이다. 위반 여부는
   `decision`(PASS/HOLD)과 화면의 "조건 유지/위반" 섹션으로 계속 확인할 수 있다.
   CARD_SPEND_SHIFT(연속 모델)는 그대로 D>0·G<0을 실제 계산해서 Action Reversal을
   보여준다 — 이 기능 자체는 지우지 않았다.
5. **퍼센트 입력창 유지 + 잘못된 순효과 판정 제거** — "새로 가입하려는 상품의 금리(%)"
   입력창은 그대로 남겼다. 다만 그 값과 기존 규칙의 %p 우대폭을 단순 차감해
   ADVANTAGEOUS/DISADVANTAGEOUS/EQUAL 배지를 매기던 로직(`net_effect_pct_p`/
   `net_effect_verdict`)은 완전히 삭제했다 — 두 값은 서로 다른 금융계약의 지표라서
   원금·잔여기간·중도해지조건 없이는 단순 비교가 성립하지 않는다. 이제는 사용자가
   입력한 값을 그대로 에코하고, `new_product_rate_note`로 "왜 자동 비교하지 않는지"를
   설명한다.
6. **시나리오 가정 노출(hist3/baseline)** — CARD_SPEND_SHIFT의 D/L/G/Safe Zone
   계산에 쓰이는 "최근 3개월 카드실적(hist3)"·"향후 월 사용액(baseline_monthly)"을
   사용자가 안 주면 대표 시나리오 기본값(22만원 x 3, 22만원)을 쓴다는 사실이 이제
   API 응답(`effects.hist3`/`effects.baseline_monthly`, `assumed` 플래그)과 화면
   문구에 명시적으로 드러난다. `linked_balance`의 기존 가정값 표시 패턴을 그대로
   따랐다.
7. **판정 범위 고지 + 문구 정리** — 모든 `/api/evaluate` 응답에 공통 문구
   `SCOPE_NOTE`("본 판정은 아래에 매칭된 등록 규칙과 입력/시나리오 범위 기준입니다")를
   추가했다. HANA_HISTORY_SAVINGS의 판정은 그대로 **PASS**를 유지하되(V5와 다른 점 —
   V5는 이걸 REVIEW로 낮췄지만, 이 규칙은 "가입 전 6개월 이력" 조건이라 현재 해지
   행동으로 애초에 훼손될 수 없어 PASS가 맞다는 판단), reason 문구를 "이 등록 규칙
   (가입 전 6개월 이력)은 현재 해지행동의 영향을 받지 않습니다. 해지 전체 손익을
   의미하지 않습니다"로 명확히 했다. "현재 유지 중인 우대폭" 문구는 "이 등록
   규칙상 우대폭"으로 다듬어 "이게 사용자의 모든 우대폭"이라는 오독 여지를 줄였다.

## 변경 파일

- `mvp/rule_store.py` — FIX 1 (매칭 로직)
- `mvp/app.py` — FIX 1~7 전체 (API 계층)
- `mvp/static/index.html` — FIX 3/4/5/6/7 화면 표시 + REVIEW-only 응답(효과 필드
  없음)에 대한 방어 렌더링 추가
- `tests/test_action_interpreter.py`, `tests/test_fix4_safezone.py`,
  `tests/test_safezone_v12.py`, `tests/test_independent_audit_20260905.py` —
  V7 동작에 맞게 갱신(과거 "잘못된 동작을 정답으로 고정한 테스트" 수정)
- `tests/test_v7_hardening.py` — 신규. `02_FINAL_TEST_AND_FREEZE.md` §A의 13개
  항목을 1:1로 커버하는 회귀 테스트 20건

## 테스트 결과

**242/242 통과, 실패 0건.** 상세는 `V7_TEST_REPORT.md` 참조.

## CODE FREEZE

이 결과물 이후 `mvp/` 코드는 동결한다. 이후 문서는 최신 코드에 맞춰 다시 쓸 것.
