# CHANGELOG

10_CHANGELOG_템플릿.md 형식을 그대로 따른다. 항목은 시간순으로 아래에 추가한다.

---

## 변경 ID
FIX-SAFEZONE-UI-001

### 문제
박승렬이 배포된 화면에서 확인한 4개 표시·정책·단위 문제
(02_FIX_1차원SafeZone_4개.md, 03_필수_회귀테스트_체크리스트.md,
04_Optimal_Safe_Range_다음단계.md, 05_최종_반환물_목록.md, 06_SELF_AUDIT.md):

1. Robust Safe Zone: "0~20,000원" 숫자 범위와 "불확실성 데이터가 없어 계산 안 함"이
   동시에 표시돼 모순으로 보임.
2. Warning Zone: robust_limit == nominal_limit일 때 "20,000원 ~ 20,000원"처럼 폭이
   0인 구간이 실제 경고구간인 것처럼 표시됨.
3. Financial Cliff(-83,333원)와 D/L/G(각 -8,333원)의 숫자가 왜 다른지 화면/API에
   설명이 없어 계산 오류처럼 보임.
4. 상단 판정 사유("2개월 뒤 전체 손익이 손실로 전환됨")와 "Action Reversal: 아니오"가
   나란히 나와서 모순처럼 읽힘(D=0이라 Action Reversal 정의(D>0,G<0)엔 안 맞지만,
   누적 G가 음수로 전환되는 것 자체는 사실).

### 변경
- `mvp/engine.py` (추가만 — 기존 함수 로직은 안 건드림):
  - `SafeZoneResult`에 `warning_status` 필드 추가(`CALCULATED`/`NONE`/
    `NOT_APPLICABLE`). `robust_value >= nominal`이면 `NONE` + warning_zone 양쪽 null.
  - `reversal_explanation(D, G, ttr)` 신규 순수 함수 — Action Reversal 정의(D>0,G<0)
    충족 여부를 D/G 값 근거로 설명하는 문구를 만든다(TTR 기준 "누적효과 음수전환"
    문구와는 별개).
- `mvp/app.py`:
  - `HORIZON_MONTHS = 12` 상수 도입, `compute_safe_zone()`/`simulate()` 호출에 명시적
    으로 전달(매직넘버 제거).
  - `/api/evaluate`의 `effects.D`/`L`/`G`를 `{value, unit, horizon_months}` 객체로,
    `safety.financial_cliff`를 `{value, unit, horizon_months}` 객체로 재구성(이산
    판정 유형은 기존처럼 `null` 그대로 — `test_safezone_v12.py`#16과 호환 확인).
  - `effects.reversal_reason` 필드 추가(연속 유형은 `reversal_explanation()` 결과,
    이산 유형은 기존 `discrete.reason` 재사용).
  - `safety.warning_status` 필드 추가.
- `mvp/static/index.html`:
  - Robust Safe Zone NOT_APPLICABLE 라벨에서 "계산 안 함" 제거 → "불확실성 정보
    없음 → Nominal Safe Zone과 동일"로 교체 + 설명 note 추가.
  - Warning Zone: `warning_status`가 NONE/NOT_APPLICABLE이면 숫자 범위 대신 "해당
    없음" 문구 표시.
  - Financial Cliff / D·L·G: 각 스탯 제목에 "(N개월 누적)" 표기, horizon이 서로
    다를 때만 "기준 시점이 달라 숫자가 차이 날 수 있습니다(계산 오류 아님)" note.
  - Action Reversal: 섹션 제목에 정의(D>0 AND G<0) 명시 + `reversal_reason` 문장을
    상단 판정 사유와 별도 줄에 표시.

DEV25 A/B/C 추출 파이프라인(`ablation/`)은 이 변경으로 전혀 건드리지 않았다 — grep
으로 `reversal_explanation`/`warning_status`/`horizon_months`가 `ablation/`에 하나도
없음을 확인함.

### 특정 테스트 맞춤 여부
NO. 새 테스트(`tests/test_fix4_safezone.py`)는 기존 test_safezone_v12.py와 동일한
합성 픽스처(KB_CARD_LOAN_STEP, HIST3=[220000,220000,220000], BASELINE=220000)를 쓴다.
DEV25 U-ID나 Gold 문자열을 참조한 곳이 없다.

### 신규/수정 테스트
`tests/test_fix4_safezone.py` (신규 파일, 24개 체크 — FIX-1~4 acceptance 항목 +
determinism + "계산 안 함" 문구 제거를 정적으로 확인). 기존 6개 테스트 파일(총 135개:
test_action_interpreter 22 / test_ai_rule 23 / test_baseline_regex 30 /
test_dev25_runner 12 / test_engine 22 / test_safezone_v12 26)은 한 줄도 수정하지
않았다.

### 결과
변경 전: 135 passed, 0 failed 6개 파일.
변경 후: 159 passed, 0 failed 7개 파일 (기존 135 + 신규 24, 회귀 없음).

### 관련 파일
- `mvp/engine.py` (추가만 — `warning_status`/`reversal_explanation`)
- `mvp/app.py` (`/api/evaluate` 응답 스키마 확장 — D/L/G·financial_cliff에 unit/
  horizon_months, reversal_reason, warning_status)
- `mvp/static/index.html` (라벨 문구 수정 + 신규 필드 반영)
- `tests/test_fix4_safezone.py` (신규)
- FREEZE_PREP.md에 이번 변경의 파일 해시를 별도로 기록함

---

## 변경 ID
FEAT-PRODUCT-001

### 문제
직전 `FEAT-INSTITUTION-001`에서 은행명 감지를 추가했는데, 사용자가 "은행명만으로
결정하면 안 되고 상품명을 봐야 한다"고 정확히 지적했다. 실제로 은행명 하나로는
상품을 특정할 수 없다 — 한 은행이 여러 상품을 취급할 수 있고(원장 37행 기준
NH농협은행도 8개 규칙을 가짐), 반대로 같은 상품군(예: "디딤돌대출")을 여러 기관이
취급할 수도 있다(주택금융공사·NH농협은행이 각자 디딤돌대출을 취급). institution
하나만으로 좁히면 이런 경우 잘못 좁혀지거나 여전히 모호할 수 있다.

### 변경
- `mvp/rule_store.py`: `match()`가 `product` 파라미터를 추가로 받는다 — institution과
  독립적으로 순서대로 좁힌다(둘 다 각자 fallback 있음: 실제 등록 안 된 이름이면 그
  단계는 무시하고 이전 후보 유지). `known_products()` 추가.
- `mvp/schemas.py`: `TypedActionDelta`에 `product: Optional[str] = None` 추가.
- `mvp/action_interpreter.py`: `PRODUCT_ALIASES`(정식 상품명→별칭)와 `_detect_product()`
  추가 — institution 감지와 완전히 같은 원칙(Gemini에게 안 맡김, 실제 등록된
  `known_products()`와만 대조, 못 찾으면 None). 부수적으로 기존 `INSTITUTION_ALIASES`의
  "하나은행" 별칭에 띄어쓰기 변형("하나 적금")이 빠져있던 걸 발견해서 같이 고쳤다.
- `mvp/app.py`: `/api/health`에 `products` 목록 추가. `/api/evaluate`가 `product`를
  받아서 `store.match(action_type, institution, product)`로 넘긴다.
- `mvp/static/index.html`: 2번 카드에 "상품명" 드롭다운을 은행 드롭다운과 별도로
  추가. 해석 결과에 institution/product가 각각 나오면 두 드롭다운을 독립적으로
  자동 선택한다(하나가 다른 하나를 대신하지 않음).

### 영향 범위
`/api/interpret`·`/api/evaluate` 요청/응답에 `product` 필드 추가(순수 추가, 하위
호환), MVP 화면 2번 카드. 지금 등록된 8개 규칙 안에서는 institution+action_type만
으로도 실제로는 항상 규칙이 하나로 좁혀지기 때문에(당장은) 체감 차이가 크지 않을
수 있지만, 원장 37행 중 아직 등록 안 된 29개(NH_SUBSCRIPTION_DIDIMDOL_* 등, 같은
"디딤돌대출"을 NH농협은행 버전으로 취급하는 규칙 포함)가 나중에 추가되면 이
independent-축 구조가 실제로 필요해진다.

### 특정 테스트 맞춤 여부
NO. `PRODUCT_ALIASES`는 demo_rules.json에 실제 등록된 5개 상품명 전부에 대해 일반적인
별칭만 등록했다. DEV25 A/B/C 파이프라인은 여전히 `TypedActionDelta`를 안 쓴다(grep
재확인 — `ablation/*.py`에 `product` 필드 참조 없음, `mvp/schemas.py`에만 있음).

### 신규/수정 테스트
`tests/test_action_interpreter.py`에 8개 체크 추가(기존 14개는 안 건드림, 총 22개) —
상품명 단독 감지 3건, institution/product 동시 감지 1건, `rule_store.match()`의
product 단독/institution+product 동시 좁힘/존재하지 않는 product의 fallback 3건.
전체 재실행 결과 기존 127개 + 신규 8개 = **135 passed, 0 failed**.

### 결과
변경 전: 은행명만으로 narrowing(상품이 여러 개면 구분 못 함).
변경 후: 은행명과 상품명을 독립된 두 축으로 감지·필터링. 135 passed, 0 failed(회귀 없음).

### 관련 파일
`mvp/rule_store.py`, `mvp/schemas.py`, `mvp/action_interpreter.py`, `mvp/app.py`,
`mvp/static/index.html`, `tests/test_action_interpreter.py`

---

## 변경 ID
FEAT-INSTITUTION-001

### 문제
사용자가 문장에 특정 은행/상품명을 언급해도(예: "신협카드로 옮길 거야") 그 정보가
어디에도 쓰이지 않았다. `action_interpreter.py`가 애초에 은행명을 추출하지 않았고
(schema에 필드 자체가 없음), 프론트도 `institution`을 서버에 보내지 않았다. 그 결과
`/api/evaluate`가 매칭되는 모든 은행 규칙을 다 끌어와서 판정했다(app.py는 원래부터
`institution` 파라미터로 좁힐 수 있게 짜여 있었는데 실제로 쓰이지 않고 있었음).

### 변경
- `mvp/schemas.py`: `TypedActionDelta`에 `institution: Optional[str] = None` 필드 추가.
- `mvp/rule_store.py`: `RuleStore.known_institutions()` 추가 — demo_rules.json에 실제로
  등록된 institution 값을 중복 제거해서 돌려준다(하드코딩 방지, 단일 출처 유지).
- `mvp/action_interpreter.py`: `INSTITUTION_ALIASES`(정식 명칭→별칭 목록)와
  `_detect_institution()` 추가. **Gemini에게 은행명 추출을 맡기지 않는다** — AI가 자유
  텍스트로 없는 은행 이름을 지어낼 수 있어서, `rule_store.known_institutions()`와
  실제로 대조하는 결정론적 키워드 매칭만 쓴다. "하나"처럼 흔한 단어 하나만으로는
  안 걸리게 "하나은행/하나카드/하나적금" 같은 복합 별칭만 등록해서 오탐을 줄였다.
  Gemini 호출이 실패해도(fail-closed NEED_INFO 경로) institution 감지는 독립적으로
  동작한다.
- `mvp/app.py`: `/api/health` 응답에 `institutions`(등록된 기관 목록) 필드 추가 —
  `/api/evaluate`는 원래부터 `institution`을 받아 좁히게 돼 있어서 수정 불필요.
- `mvp/static/index.html`: 2번 카드에 은행/상품 선택 드롭다운 추가(옵션은 `/api/health`
  응답으로 자동 채움). "해석하기"로 문장에서 은행명이 감지되면 드롭다운을 자동
  선택하고, "검증 실행" 때 그 값을 `/api/evaluate`에 같이 보낸다.

### 영향 범위
`/api/interpret`·`/api/evaluate` 요청/응답에 `institution` 필드 추가(기존 필드는
안 건드림 — 순수 추가라 하위 호환됨), MVP 화면 2번 카드. 알려진 한계: 문장에 은행이
두 곳 언급되면(예: "KB카드에서 신협카드로 옮길 거야") 더 긴 별칭 쪽이 선택된다 —
이번 예시에서는 우연히 "카드실적이 줄어드는 쪽(KB)"이 선택돼 의미상 맞았지만,
일반적으로 보장되는 동작은 아니다. 존재하지 않는 은행명이 들어와도 `rule_store.
match()`가 원래 갖고 있던 fallback(좁혀서 매칭 0건이면 전체 후보로 복귀)이 그대로
적용돼 안전하다.

### 특정 테스트 맞춤 여부
NO. 별칭표는 demo_rules.json에 실제 등록된 5개 기관(KB국민은행/주택금융공사/
케이뱅크/신협/하나은행) 전부에 대해 일반적인 별칭만 등록했고, DEV25 U-ID나 특정
질문에 맞춘 것이 아니다. DEV25 A/B/C 추출 파이프라인은 `TypedActionDelta`를 전혀
쓰지 않는다(grep으로 확인 — `ablation/*.py` 어디서도 import 안 함) — 이번 변경은
MVP 전용 경로에만 영향을 준다.

### 신규/수정 테스트
`tests/test_action_interpreter.py`에 6개 체크 추가(기존 8개는 안 건드림, 총 14개) —
등록된 기관 감지 3건, 일반 단어 오탐 방지 1건, 은행명 없는 문장 1건, 별칭을 통한
정식 명칭 매칭 1건. 전체 재실행 결과 기존 121개 + 신규 6개 = **127 passed, 0 failed**.

### 결과
변경 전: 문장에 은행명을 써도 무시됨(전체 후보로만 판정).
변경 후: 등록된 5개 기관 중 하나가 언급되면 자동 인식돼 그 기관 규칙으로 좁혀서
판정(수동으로 드롭다운 선택도 가능). 127 passed, 0 failed(회귀 없음).

### 관련 파일
`mvp/schemas.py`, `mvp/rule_store.py`, `mvp/action_interpreter.py`, `mvp/app.py`,
`mvp/static/index.html`, `tests/test_action_interpreter.py`

## 변경 ID
MATH-V12-001

### 문제
기존 engine.py는 "이 계약(하나)의 안전한도 하나"만 계산했다(safe_limit()). 여러 계약이
동시에 매칭되는 실제 상황에서 어느 계약이 진짜로 먼저 문제가 되는지(binding constraint),
계획 행동이 "확인된" 상태 불확실성까지 감안해도 안전한지(robust vs nominal), 경계를
넘는 순간 손익이 얼마나 점프하는지(financial cliff), 손실 없이 최대로 움직일 수 있는
범위가 어디인지(optimal safe range)를 계산/표시할 방법이 없었다. 박승렬이 02~07번
문서로 이 수학(Safe Zone v1.2)을 명세하고, 08번 문서로 DEV25 파이프라인을 건드리지
말라는 보호규칙을 함께 내려보냈다.

### 변경
- `mvp/engine.py`: 기존 함수(`simulate`/`safe_limit`/`decide`/`build_rolling_series`/
  `tier_lookup` 등)는 한 글자도 수정하지 않고, `compute_safe_zone()`을 새로 추가했다.
  Nominal Safe Limit(여러 계약 중 최솟값), Robust Safe Limit(확인된 불확실성
  시나리오가 있을 때만 계산 — 없으면 임의 버퍼를 만들지 않고 `robust_status=
  NOT_APPLICABLE`로 정직하게 표시), Robust/Warning Zone, 현재 행동의 zone 판정(SAFE/
  WARNING/BREACH/REVIEW), Binding Constraint(동률이면 전부 배열로 반환), Financial
  Cliff(실제 불연속이 없으면 `NOT_APPLICABLE`), Optimal Safe Range(G 계산 근거 없으면
  `UNKNOWN_EFFECT`)를 구현했다. 전 구간에서 "모르면 unknown/NOT_APPLICABLE로 남긴다"
  원칙을 지켰다 — 값을 추정해서 채운 곳이 없다.
- `mvp/app.py`: `/api/evaluate`가 매칭된 계약 전부를 `compute_safe_zone()`에 넘기고,
  05_API_응답_권장스키마.json 형식(`action`/`effects`/`safety`/`time`/`evidence`(배열)/
  `engine_meta`)으로 응답한다. 부수 발견: 기존 코드는 다중 계약 중 "첫 번째로 매칭된"
  계약만 기준으로 TTB/TTR을 계산했는데, 이번에 실제로 binding(가장 엄격한) 계약
  기준으로 바꿨다 — 이건 수학 확장이 아니라 기존 로직의 정확성 버그 수정이다.
- `mvp/static/index.html`: 06_MVP_표시명세.md의 12개 항목 순서 그대로 표시하도록
  다시 짰다. 프론트는 아무 것도 재계산하지 않고 API가 준 값을 그대로 옮긴다. 값이
  없으면 "0원"이 아니라 "확인 필요"/"계산에 필요한 정보 부족"으로 표시한다.
- `demo_rules.json`/`README.md`/`FREEZE_PREP.md`: (이번 수학 작업과 별개 건) 8/28
  최초 원장 대조에서 unverified로 플래그했던 3건(HANA_HISTORY_SAVINGS, SHINHYUP_
  CARD_USAGE 하위구간, HF_SUBSCRIPTION_DIDIMDOL 신혼부부 금리하한)을 박승렬이 원본
  출처로 재확인해줘서, 플래그를 해제하고 근거를 남겼다.

### 영향 범위
`CARD_SPEND_SHIFT` 유형(1차원 연속 금액 행동)의 `/api/evaluate` 응답과 MVP 화면 표시.
`PRODUCT_TERMINATION`/`PAYMENT_ACCOUNT_CHANGE`/`SALARY_ACCOUNT_CHANGE`(이산 판정)는
새 스키마의 형태만 맞추고(`safety.current_zone="NOT_APPLICABLE"` 등) 계산 로직은
그대로다 — Safe Zone 개념 자체가 이 유형들엔 적용되지 않는다(명세에 정의가 없음).
DEV25 A/B/C 추출 파이프라인(`ablation/dev25_runner.py`, `ablation/wide_compiler.py`,
`mvp/schemas.py`)은 이 변경으로 전혀 건드리지 않았다 — grep으로 새 Safe Zone 필드명이
그 파일들에 하나도 없음을 확인함(아래 "특정 테스트 맞춤 여부" 참고).

### 특정 테스트 맞춤 여부
NO.

새 테스트(tests/test_safezone_v12.py) 25건은 전부 KB_CARD_LOAN_STEP과 동일한 형식의
합성(synthetic) 임계값표(KB/STRICT/FLAT/BUMP/EARLY/LATE)와 test_engine.py에 이미 있던
공통 픽스처(HIST3=[220000,220000,220000], BASELINE=220000)로 만들었다. DEV25의 특정
U-ID(U001~U025)나 Gold 문자열을 하드코딩하거나 참조한 곳이 없다 — 실제로
`ablation/dev25_runner.py`/`ablation/wide_compiler.py`/`mvp/schemas.py`를 grep해서
새 Safe Zone 관련 필드명(safe_zone/compute_safe_zone/robust_safe/nominal_safe/
binding_constraint/financial_cliff/optimal_safe 등)이 전혀 없음을 확인했다(매치 0건).
또한 이 수학엔진 테스트 결과(26개 전부 통과)는 DEV25 AI 추출 성능과 무관하다 — DEV25
System B의 공식 25건 실행은 이번 변경에 포함되지 않았고(08_DEV25_보호규칙 §2 — B
원본 프롬프트는 확정됐지만 유료 API 키가 아직 없어 미실행), C도 여전히 Gemini
재호출 0회임을 `ablation/dev25_checkpoint.jsonl`의 175행 전부 `http_status=null`로
재확인했다(§3).

### 신규/수정 테스트
`tests/test_safezone_v12.py` (신규 파일, 26개 체크 — 04_신규_회귀테스트_명세.md의
필수 25개 케이스 전부 포함, 5번 항목만 "불확실성 있음/없음" 두 하위 케이스로 나눠서
검증). 기존 5개 테스트 파일(test_engine.py 22 / test_ai_rule.py 23 /
test_baseline_regex.py 30 / test_dev25_runner.py 12 / test_action_interpreter.py 8 =
95개)은 한 줄도 수정하지 않았다. 각 테스트는 input/expected/actual/pass-fail을
`tests/safezone_v12_evidence.json`에 저장한다.

### 결과
변경 전: 95 passed, 0 failed 5개 파일.
변경 후: 121 passed, 0 failed 6개 파일 (기존 95 + 신규 26, 회귀 없음).

### 관련 파일
- `mvp/engine.py` (추가만 — `compute_safe_zone`/`ConstraintLimit`/`SafeZoneResult`/
  `ENGINE_VERSION="engine_v1.2_safezone_2026-08-28"`)
- `mvp/app.py` (`/api/evaluate` 응답 스키마 확장 + binding 계약 기준 버그 수정)
- `mvp/static/index.html` (표시 순서 12항목 재구성)
- `tests/test_safezone_v12.py` (신규)
- `tests/safezone_v12_evidence.json` (신규, 테스트 실행 시 자동 생성)
- FREEZE_PREP.md에 이번 변경의 파일 해시를 별도로 기록함(§자유서 참고)
