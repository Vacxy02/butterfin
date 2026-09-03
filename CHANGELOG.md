# CHANGELOG

10_CHANGELOG_템플릿.md 형식을 그대로 따른다. 항목은 시간순으로 아래에 추가한다.

---

## 변경 ID
FREEZE-CANDIDATE-FINAL-PRE-SANITY-2026-08-31

### 배경
박승렬의 "Butterfin - 동학 최종 수정 요청"(기준: Claude 검증회신 2026-08-31 오후,
목표: sanity rerun 직전 Freeze 후보 마감) 지시 반영. API 재실행/FINAL_UNSEEN/
prompt·Gold·schema 튜닝/특정 U-ID 특례 없이 일반 규칙으로만 4개 항목 반영. 각 항목
1줄:

- `mvp/ai_rule.py` + `ablation/wide_compiler.py` + `ablation/dev25_runner.py` +
  `ablation/scoring_contract.md` + `README.md` + `tests/test_ai_rule_openai_provider.py`:
  공식 System B provider를 GPT로 확정 — "GPT 실험용/비공식/공식 Gemini 결과 아님"
  라벨을 전부 "DEV25 공식 System B — GPT, 2026-08-31 확정"으로 교체. 이미 완료된
  DEV25 25×3 GPT 실행 결과가 공식 블라인드 재채점 대상이 됨(DEV25는 development
  benchmark로 계속 유지, FINAL_UNSEEN 아님). `dev25_runner.py`의 공식/참고 출력
  파일명을 뒤집음(`AI_PROVIDER=openai`→`DEV25_RESULTS.xlsx`=공식,
  gemini→`DEV25_RESULTS_GEMINI_REFERENCE.xlsx`=참고). `AI_PROVIDER` 기본값은
  여전히 `"gemini"`이고 `_MODEL`/`api_key_present()`/`live_status()`(별도
  라이브 데모용)는 손대지 않음 — 순수 명칭/문서 정합화이며 GPT 결과 숫자를 보고
  prompt/model을 바꾼 것은 아님.
- `ablation/dev25_runner.py`: EVAL_STRICT 실행 사실을 결과물에 기록 — `run()` 시작
  시 콘솔에 `EVAL_STRICT=.../AI_PROVIDER=...` 로그 출력, checkpoint와 나란히
  `dev25_run_metadata_<provider>.json`을 써서 eval_strict/provider/시작·종료
  시각/status/총행수/is_mock 기록(xlsx 컬럼 대신 metadata 파일 방식 선택 — schema
  변경 회피). `--require-eval-strict` CLI 플래그(기본 off) 추가 — 지정 시
  EVAL_STRICT=1이 아니면 fail-fast로 실행 자체를 중단.
- `mvp/static/index.html`: TTB 표시 라벨을 "TTB (구간 이탈 시점)" →
  "TTB (우대 조건이 깨지는 시점)"으로 수정(TTR 라벨은 기존 수정본 유지).
- `action_reversal_rule_ledger_v3.csv`: 신원 승인 항목 A~D 반영, 37행→39행.
  `HANA_HISTORY_SAVINGS`(effect_value=4.7/effect_kind=rate_bonus로 정정),
  `SHINHYUP_CARD_USAGE`→`SHINHYUP_CARD_USAGE_T2`(threshold 1→8 정정 — 행 자체의
  기존 evidence_span/clause_locator가 이미 "8회 이상"을 근거로 명시), 신규
  `SHINHYUP_CARD_USAGE_T1`(4~7회, 2.5%p), 신규 `HF_RATE_FLOOR_NEWLYWED`(생애최초
  신혼가구 최종금리 하한 1.2%). 값은 전부 `mvp/demo_rules.json`의 기존
  `ledger_reconfirmed_2026-08-28`(승렬 확정자료)를 그대로 사용 — 신규 조사 없음.
  최종 행수는 미리 선언하지 않고 반영 후 재측정함.

### 하지 않은 것 (지시대로)
API 재실행 0회. sanity rerun 없음. FINAL_UNSEEN 미수집/미작성/미노출. prompt/schema/
Gold 변경 없음. 특정 U-ID/DEV25 문항 전용 예외 없음.

### 검증
`for f in tests/*.py; do AR_ROOT=$(pwd) python3 "$f"; done` — **190 passed, 0 failed**
(9개 파일, `test_ai_rule_openai_provider.py`의 라벨 단언문 갱신 포함 전부 통과, 기존
대비 회귀 없음). `evidence_bundle_check.py`는 최초에는 저장소에 없어(find/grep 확인)
대체 스크립트(`/root/work/grounding_check.py`)로만 검증했으나, 동학이 실제 파일을
전달해서 정식 스크립트로 재검증했다. 첫 실행은 **실패(exit 1, 46/49)** —
`HANA_HISTORY_SAVINGS`/`SHINHYUP_CARD_USAGE_T1`/`SHINHYUP_CARD_USAGE_T2`의
effect_value가 원장-번들(`evidence_bundle_20260821.csv`) rule_id 불일치로 접지
안 됨(원장 rule_id를 개명/신규 추가하면서 번들을 같이 안 갱신한 게 원인, 값 자체는
`demo_rules.json`의 기존 확정 인용문 그대로 옳았음). 번들 CSV를 같은 rule_id로
동기화(신규 조사 없음, 기존 확정 인용문만 사용)한 뒤 재실행 — **전체 활성 필드
접지 89/89 (100%), exit 0 통과**. 상세는 FREEZE_PREP.md "최종 수정 요청 반영" 절
참고.

### 관련 파일
- `mvp/ai_rule.py`, `ablation/wide_compiler.py`, `ablation/dev25_runner.py`,
  `ablation/scoring_contract.md`, `README.md`, `tests/test_ai_rule_openai_provider.py`
  (GPT 공식화 라벨링)
- `ablation/dev25_runner.py` (EVAL_STRICT metadata 기록 + `--require-eval-strict`)
- `mvp/static/index.html` (TTB 라벨)
- `action_reversal_rule_ledger_v3.csv` (39행)
- `evidence_bundle_20260821.csv` (rule_id 동기화 — SHINHYUP_CARD_USAGE_T1 신규/
  HANA_HISTORY_SAVINGS rate_evidence_span 보강, `evidence_bundle_2026-08-21.csv`
  하이픈 별칭 사본 포함)
- `evidence_bundle_check.py` (동학 전달, 리포지토리에 신규 추가)
- FREEZE_PREP.md에 이번 변경의 파일 해시를 별도로 기록함

---

## 변경 ID
FREEZE-CANDIDATE-PREP-2026-08-31

### 배경
박승렬의 "Butterfin - 동학 다음 작업팩"(2026-08-31) 지시 반영. API 재실행/Gold 튜닝/
U-ID 특례 없이 Freeze 후보 코드만 정리. 각 항목 1줄:

- `mvp/static/index.html`: TTR 표시 라벨을 "TTR (실제 위반 시점)" → "TTR (누적 전체효과가
  손해로 전환되는 시점)"으로 수정 (engine.py의 실제 정의와 그동안 라벨이 안 맞았음).
- `ablation/dev25_runner.py`: checkpoint 파일을 provider별로 분리
  (`dev25_checkpoint_gemini.jsonl` / `dev25_checkpoint_openai.jsonl`) — provider 전환 시
  옛 provider 결과가 같은 (sample_id, system, run_id) 키로 조용히 재사용/skip되는 위험 제거.
- `mvp/ai_rule.py` + `ablation/wide_compiler.py`: `EVAL_STRICT=1`(공식 평가모드) 추가 —
  live 실패 시 과거 cache로 대체하지 않고 `SOURCE_RUN_FAILURE`로 표시, 429/5xx/timeout/
  network만 재시도, HTTP 200이어도 스키마/내용 검증 실패면 `reject_reason`에
  "RUN_FAILURE (EVAL_STRICT)"로 명시(둘 다 cache 대체 없음). 기본값(EVAL_STRICT=0)에서는
  기존 데모/개발 모드 cache-fallback 동작 그대로.
- `ablation/blind25_fixed.py`: self-check에 남아 있던 U005 원문(source_bundle_text)을
  DEV25 밖 합성 예시로 교체 — 이 self-check은 캐시/API를 안 타서 결과 오염 문제는
  아니었고 Freeze 패키지 위생 정리.
- `ablation/scoring_contract.md`: 구 16필드/Field-Exact Rule Match 정의를 폐기하고,
  "DEV25 v1.1 LOCK + 박승렬 측 `dev25_scoring_v11.py`가 canonical scoring contract"임을
  명시하는 참조문서로 교체(수식은 이 리포지토리가 임의로 재정의하지 않음).
- `ablation/dev25_runner.py`: checkpoint의 `error_log`를 문자열 `"[]"`가 아니라 실제
  list 타입으로 직렬화(xlsx 저장 시에만 문자열로 변환).
- Freeze Candidate ZIP에 `ablation/baseline_regex.py`(System A 실제 사용 코드)를 SHA256과
  함께 포함.

### 하지 않은 것 (지시대로)
API 재실행 0회. FINAL_UNSEEN 미수집. Gold/현재 결과 기반 튜닝 없음. U001/U002/U004/U013
전용 코드 없음. 원장 반영(HANA/SHINHYUP/HF 항목)은 신원 승인 전이라 보류.

### 검증
`for f in tests/*.py; do AR_ROOT=$(pwd) python3 "$f"; done` — **189 passed, 0 failed**
(기존과 동일, 회귀 없음).

### 추가 (2026-08-31, 동일 세션 후속)
승렬 측 실제 `dev25_scoring_v11.py`를 전달받아 `ablation/dev25_scoring_v11.py`로 추가.
`dev25_runner.py` mock 실행 xlsx로 구조 호환 확인(sheet명 "DEV25_RESULTS", sample_id/
system/run_id/accepted/schema_valid 컬럼 매칭) — Gold 없이 구조만 검증, 채점 수치는
만들지 않음. `scoring_contract.md`에 반영.

---

## 변경 ID
FIX-DEV25-OPENAI-STRICT-SCHEMA-001

### 문제
FEAT-DEV25-OPENAI-EXPERIMENT-001을 실제로 써봤다 — 동학이 실제 유료
`OPENAI_API_KEY`로 `AI_PROVIDER=openai AR_ROOT=$(pwd) python ablation/dev25_runner.py
--fresh`를 돌려서 `DEV25_RESULTS_OPENAI_EXPERIMENTAL.xlsx`를 받았는데, 결과를 열어보니
System A(25건)만 정상이고 **System B 75건이 전부 `accepted=N`, `http_status=400`**
이었다(System C 75건도 "B 추출 실패로 Gate 적용 대상 없음"으로 연쇄 실패). 실제 GPT
실험을 처음으로 돌려본 것이었는데, 첫 실행부터 100% 실패였다.

`reject_reason`을 봐도 `"HTTPError: HTTP Error 400: Bad Request"`라고만 찍혀 있어서
OpenAI가 정확히 뭘 거부했는지 알 수 없었다 — 원인 진단 자체가 막혀 있었다(이건 그
자체로 두 번째 버그).

### 변경
`mvp/ai_rule.py`에서 원인 2가지를 찾아 고쳤다.

1. **`_gemini_schema_to_openai_strict()`가 최상위 필드만 변환하고 있었다.** DEV25
   System B의 실제 스키마(`ablation/wide_compiler._WIDE_SCHEMA`)에는
   `tiers: {type: array, items: {type: object, properties: {threshold,
   effect_value}}}`처럼 배열 안에 object가 중첩돼 있는데, OpenAI strict
   구조화 출력 모드는 **모든** object(중첩된 것 포함)에
   `additionalProperties: false` + 그 object 자신의 전체 필드를 `required`에
   넣을 것을 요구한다. 최상위만 변환했더니 `tiers.items`가 이 조건을 못
   만족해서 API가 요청 자체를 400으로 거부했다 — System B 75건 전원이 같은
   이유로 실패한 것이 바로 이거였다. 변환 함수를 재귀적으로 고쳐서
   object/array 어느 깊이에 있든 strict 조건을 채우도록 했다.
2. **`_call_openai()`가 `HTTPError`의 응답 본문을 안 읽고 있었다.**
   `str(e)`만 쓰면 "HTTP Error 400: Bad Request"라는, OpenAI가 실제로 뭐라고
   답했는지 전혀 알 수 없는 문구만 남는다(이 파일 상단에 이미 있던
   2026-08-18 Gemini 404 사례 — "except가 삼키는 바람에 원인이 안 보였다" —
   와 정확히 같은 실패 패턴). `except urllib.error.HTTPError`를 별도로 잡아서
   `e.read()`로 실제 오류 본문(스키마 위반 상세 메시지 등)을 `_LAST_ERROR`에
   남기도록 고쳤다 — 다음에 비슷한 실패가 나도 원인을 바로 알 수 있다.

캐시 네임스페이스 분리/라벨링/산출 파일명 분리(FEAT-DEV25-OPENAI-EXPERIMENT-001)는
이 버그와 무관하게 그대로 유지된다 — 이번 수정은 어디까지나 "GPT 호출 자체가
성공하도록" 고친 것이다.

### 특정 테스트 맞춤 여부
NO — 다만 이번엔 실제 유료 API 실행에서 나온 실측 실패(75건 전원 400)를 계기로
찾은 버그라, 회귀테스트도 그 실측 실패를 재현하는 형태로 만들었다. 실제 OpenAI
네트워크 호출은 여전히 하지 않는다(스키마 변환은 순수 함수 검증, HTTPError 처리는
`unittest.mock.patch`로 urlopen을 가짜 400 응답으로 대체해 검증).

### 신규/수정 테스트
`tests/test_ai_rule_openai_provider.py`에 섹션 8 추가(4개 체크 — 17개 → 21개):
`_gemini_schema_to_openai_strict()`가 실제 `_WIDE_SCHEMA`의 `tiers.items`에도
`additionalProperties=false`/전체 `required`를 재귀적으로 채우는지, `_call_openai()`
가 가짜 400 HTTPError(본문 포함)를 받았을 때 `last_error()`에 그 본문이 실제로
담기는지를 각각 확인. 기존 185개 테스트는 한 줄도 수정하지 않았다.

### 결과
변경 전: 185 passed, 0 failed 9개 파일 (그리고 실제 키로 돌린 DEV25 실행은 System B/C
150건 전부 실패).
변경 후: 189 passed, 0 failed 9개 파일 (기존 185 + 신규 4, 회귀 없음). 실제 25건
재실행은 동학이 `--fresh`로 다시 돌려서 직접 확인 예정 — 이 세션은 실제
`OPENAI_API_KEY`를 갖고 있지 않아 실제 네트워크 성공 여부까지는 검증하지 못했다.

### 관련 파일
- `mvp/ai_rule.py` (`_gemini_schema_to_openai_strict()` 재귀 변환, `_call_openai()`
  HTTPError 본문 캡처)
- `tests/test_ai_rule_openai_provider.py` (섹션 8 추가)
- FREEZE_PREP.md에 이번 변경의 파일 해시를 별도로 기록함

---

## 변경 ID
FEAT-DEV25-OPENAI-EXPERIMENT-001

### 문제
FEAT-OPENAI-PROVIDER-001에서 라이브 데모(action_interpreter.py)만 GPT로 바꿀 수
있게 했을 때, "그럼 DEV25도 그냥 바꾸면 안 되나"는 질문이 이어졌다. 바로 답을
드리는 대신 위험 3가지를 먼저 설명했다: (1) prompt-model 결합 — System B 프롬프트는
Gemini 응답 특성 기준으로 확정된 것이라 모델을 바꾸면 그 확정이 무효가 됨,
(2) 스키마 강제 메커니즘 차이 — Gemini의 `response_schema`(SDK 서버측 강제)와
OpenAI의 `json_schema`+`strict`(다른 강제 방식, 특히 optional 필드 처리 방식이 다름)
가 서로 달라서 "정확도 차이"처럼 보이는 게 실은 모델 차이가 아니라 스키마 강제
방식 차이일 수 있음, (3) 공식 제출 신뢰/라벨링 문제 — GPT로 뽑은 결과가 공식
Gemini 결과와 섞이거나 혼동되면 심사 신뢰성 문제로 번짐. 동학이 이 설명을 듣고
"결과 파일명/로그에 GPT 실험용이라고 확실히 표시해서 공식 Gemini 결과랑 절대 안
섞이게 한다"는 조건으로 명시적으로 승인("그래") — 이번 변경은 그 조건을 실제
코드로 지킨 것이다.

### 변경
DEV25 System B/C의 실제 추출 모듈인 `mvp/ai_rule.py`(박승렬 작성)에 실험용
`AI_PROVIDER` 스위치를 추가했다. FEAT-OPENAI-PROVIDER-001과 같은 패턴(기본값
`"gemini"`, 안 건드리면 기존 동작 100% 동일)이되, "공식 결과와 절대 안 섞이게"라는
조건 때문에 세 가지 격리 장치를 추가로 넣었다.

- `mvp/ai_rule.py`:
  - `AI_PROVIDER`/`_OPENAI_MODEL`/`_OPENAI_API_KEY_ENV` 상수 추가.
  - `_active_model_name()` 신규 — `_MODEL`(공식 Gemini 준비 상태 판정에 쓰이는
    상수, **안 건드림**)과 분리된, "이번 호출에 실제로 어떤 모델을 썼는지"
    라벨링 전용 함수. `AI_PROVIDER=openai`면
    `"gpt-4o-mini (GPT 실험용 — 비공식, 공식 Gemini 결과 아님)"`처럼 명시적으로
    표시한다.
  - `_active_key_present()` 신규 — `api_key_present()`(공식, Gemini 전용, **안
    건드림**)와 분리된, 실제 쓰이는 provider의 키 유무 판정 전용 함수.
  - `_cache_path()`: `AI_PROVIDER=openai`면 캐시 파일명에 `_openai_` 네임스페이스를
    끼워서 Gemini 캐시와 파일명 자체가 절대 겹치지 않게 함.
  - `_gemini_schema_to_openai_strict()` 신규 — Gemini의 partial-required 스키마를
    OpenAI strict 모드(전체 required + `additionalProperties: false`) 형식으로
    변환. optional이던 필드는 nullable로 만들어 "생략 가능" 의미를 보존한다.
  - `_call_openai()`/`_call_ai()` 신규 — `_call_gemini()`(**안 건드림**)와 동일한
    fail-closed 계약(네트워크/키 오류를 조용히 삼키지 않고 `_LAST_ERROR`에 남김).
  - `_invoke()`: `_call_gemini()` 직접 호출 → `_call_ai()` 경유로 한 줄 변경(내부
    분기만 추가, 캐시 fallback 로직 등 나머지는 그대로).
  - `api_key_present()`/`live_status()`/`_MODEL`은 의도적으로 **전혀 안 건드림** —
    "준비됨" 표시가 GPT 설정 때문에 거짓으로 뜨는 일이 구조적으로 불가능하다.
- `ablation/wide_compiler.py`: `compile_raw()`의 `model_name` 라벨이 `ai_rule._MODEL`
  을 직접 참조하던 것을 `ai_rule._active_model_name()`으로 교체. (안 고쳤으면
  `AI_PROVIDER=openai`로 돌려도 DEV25 결과 xlsx의 `model_name` 컬럼에 계속
  "gemini-3.6-flash"라고 찍혀서, 정작 라벨링 약속이 이 지점에서 깨졌을 것 —
  검증 중 직접 발견하고 이번 라운드에서 같이 고쳤다.)
- `ablation/dev25_runner.py`:
  - `is_mock` 판정을 `ai_rule.live_status()["ready"]`(Gemini 전용) 대신
    `ai_rule._active_key_present()`(provider-aware)로 교체 — 안 고쳤으면
    `AI_PROVIDER=openai`+`OPENAI_API_KEY`로 실제 라이브 호출에 성공해도
    "GEMINI_API_KEY 없음"이라고 잘못 찍었을 것.
  - `__main__`: `AI_PROVIDER=openai`면 출력 파일을 `DEV25_RESULTS.xlsx`가 아니라
    `DEV25_RESULTS_OPENAI_EXPERIMENTAL.xlsx`로 분리 저장 — 공식 산출물을 절대
    덮어쓰지 않는다. 실행 시작 시 "GPT 실험용, 공식 결과 아님" 경고를 콘솔에
    명확히 출력.

**공식 25문항 Gemini 실행(파이프라인의 실제 목적)은 이 변경으로 전혀 달라지지
않는다** — `AI_PROVIDER`를 아무도 설정하지 않으면 `ai_rule.py`/`wide_compiler.py`/
`dev25_runner.py`의 모든 분기가 이전과 정확히 같은 값을 반환한다
(`tests/test_ai_rule_openai_provider.py` #1~3에서 직접 확인).

### 특정 테스트 맞춤 여부
NO. `tests/test_ai_rule_openai_provider.py`는 서브프로세스로 실제 환경변수를
바꿔가며 검증하며(같은 프로세스에서 `os.environ`만 바꾸는 방식은 모듈 로드 시점
상수라 재적용 안 됨), 실제 네트워크 호출은 하지 않는다(OpenAI 쪽은 키 없을 때의
fail-closed 경로만, Gemini 쪽은 기존과 동일한 mock/cache 경로만 검증). U-ID나
Gold 문자열을 참조하지 않는다.

08_DEV25_보호규칙의 "DEV25 파일은 새 세션 심볼을 참조하면 안 된다"는 일반 원칙과
이번 라운드는 성격이 다르다는 점을 분명히 한다: 이번엔 동학이 `ai_rule.py` 자체를
실험적으로 확장하는 것을 명시적으로 승인했으므로, 검증 대상은 "안 건드렸는지"가
아니라 "건드린 부분이 공식 경로로부터 안전하게 격리되는지"다 — 위 세 가지 격리
장치(공식 판정 함수 불변/ 캐시 네임스페이스 분리 / 라벨링)가 그 검증 대상이다.

### 신규/수정 테스트
`tests/test_ai_rule_openai_provider.py` (신규 파일, 17개 체크 — 기본값 불변,
공식 판정 함수(`api_key_present`/`live_status`/`_MODEL`) 불변, 캐시 네임스페이스
분리, `ai_rule.compile_rule()`/`wide_compiler.compile_raw()` 라벨링,
`dev25_runner`의 `_active_key_present()` 기반 판정, 출력 파일명 분리). 기존 168개
테스트는 한 줄도 수정하지 않았다.

### 결과
변경 전: 168 passed, 0 failed 8개 파일.
변경 후: 185 passed, 0 failed 9개 파일 (기존 168 + 신규 17, 회귀 없음).

### 관련 파일
- `mvp/ai_rule.py` (`AI_PROVIDER` 스위치 + 격리 장치 3종 추가)
- `ablation/wide_compiler.py` (`model_name` 라벨링을 `_active_model_name()` 경유로 수정)
- `ablation/dev25_runner.py` (`is_mock` 판정 수정, 출력 파일명 분리, 경고 문구 추가)
- `tests/test_ai_rule_openai_provider.py` (신규)
- FREEZE_PREP.md에 이번 변경의 파일 해시를 별도로 기록함

---

## 변경 ID
FEAT-OPENAI-PROVIDER-001

### 문제
"GEMINI_API_KEY 대신 GPT(OpenAI) API로 바꾸면 쉬운가"라는 질문. Gemini 유료 키가 아직
없는 상황에서, 라이브 데모(action_interpreter.py의 문장 해석)만이라도 GPT로 돌릴 수
있으면 좋겠다는 요청.

### 변경
- `mvp/openai_client.py` (신규): `mvp/gemini_client.py`와 정확히 같은 인터페이스
  (`call_openai_json`/`has_api_key`/`OpenAIError`)로 OpenAI Chat Completions를
  호출한다. SDK 의존성 없이 `urllib`만 쓴다(gemini_client.py와 동일한 방식). 키가
  없으면 네트워크 호출 없이 바로 `OpenAIError`.
- `mvp/action_interpreter.py`: `AI_PROVIDER` 환경변수(기본값 `"gemini"`)로 Gemini/GPT를
  선택하는 얇은 분기(`_ai_has_key`/`_ai_call`/`_ai_model_name`)를 추가했다.
  `AI_PROVIDER`를 아무도 안 건드리면 기존 동작이 한 글자도 안 바뀐다(기본값이
  `"gemini"`라서 기존 `gemini_client` 경로 그대로 탐). `AI_PROVIDER=openai` +
  `OPENAI_API_KEY`를 주면 그쪽으로 분기한다. 은행/상품명 감지(institution/product)는
  이 분기와 완전히 무관하게 그대로 동작한다(원래도 AI 호출과 독립적인 결정론적
  로직이었음 — 안 건드림).
- `.env.example`, `render.yaml`, `README.md`: `AI_PROVIDER`/`OPENAI_API_KEY`/
  `OPENAI_MODEL` 설정 위치를 문서화.

**DEV25 System B/C(`ablation/wide_compiler.py` → `mvp/ai_rule.py`)는 이 변경에
포함하지 않았다.** 그쪽 B 프롬프트는 이미 Gemini 기준으로 팀이 확정한 것이라(08_
DEV25_보호규칙 §2), 모델을 바꾸면 그 확정 자체가 무효가 된다 — 박승렬 확인 없이는
손대지 않는다는 원칙을 그대로 지켰다. `mvp/ai_rule.py`는 여전히 `GEMINI_API_KEY`/
`GEMINI_MODEL`만 읽는다(변경 없음, grep으로 재확인: `ablation/`에 `openai`/`OPENAI`/
`AI_PROVIDER` 참조 0건).

### 특정 테스트 맞춤 여부
NO. `tests/test_openai_provider.py`는 실제 네트워크 호출 없이(키 없을 때의 결정론적
fail-closed 경로만) 검증한다 — 진짜 OpenAI API를 실제로 때리는 테스트는 CI에서
재현 불가능해질 수 있어 자동화 회귀테스트에 넣지 않았다.

### 신규/수정 테스트
`tests/test_openai_provider.py` (신규 파일, 9개 체크 — provider 분기 기본값/openai
전환/알 수 없는 값 안전 처리/은행명 감지 독립성/openai_client 키 유무 계약). 기존
159개 테스트는 한 줄도 수정하지 않았다.

### 결과
변경 전: 159 passed, 0 failed 7개 파일.
변경 후: 168 passed, 0 failed 8개 파일 (기존 159 + 신규 9, 회귀 없음).

### 관련 파일
- `mvp/openai_client.py` (신규)
- `mvp/action_interpreter.py` (`AI_PROVIDER` 분기 추가)
- `tests/test_openai_provider.py` (신규)
- `.env.example`, `render.yaml`, `README.md` (문서화)
- FREEZE_PREP.md에 이번 변경의 파일 해시를 별도로 기록함

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

---

## 2026-09-02 — Run O sanity rerun provenance / Freeze documentation closeout

### 성격
문서·메타데이터 기록만 추가. 코드·prompt·schema·Gate·Gold·canonical scorer·Run E 결과·블라인드 채점 점수는 변경하지 않았다. API 재호출 및 재채점 없음.

### Run O 기록
- 실행 시각: 2026-08-31 17:43~17:48 KST
- 실행자: 이동학
- 명령: `AI_PROVIDER=openai EVAL_STRICT=1 AR_ROOT=$(pwd) python ablation/dev25_runner.py --require-eval-strict --fresh`
- 결과: `DEV25_RESULTS.xlsx`
- SHA256: `9e4bd6eb764a76641168e9802a78571532da046645600d9c826c65f663c3d5d6`
- run_metadata SHA256: `c120cbe6073282f265680e907bfe24ab646f69f22249ed56156196e62a74905c`
- checkpoint SHA256: `3e7309e9a2e4a3eaac8696dd723a58a4491de0a182c62e4678b9fd77f0472c76`
- console log SHA256: `2630bfc8801bbf0c11140e2c822e44ed92fa5a1a4e7a099bdcdc9bfc861f7287`
- 실행 상태: `EVAL_STRICT=true`, `AI_PROVIDER=openai`, `is_mock=false`, 175행(A25/B75/C75), B HTTP 200 75/75, retry 0, C는 B 저장출력 75/75 재사용(API 재호출 0).

### 공식성
Run O는 **재현성 reference run**으로만 보관한다. 공식 DEV25 headline 산출에는 사용하지 않는다. 공식 블라인드 채점 대상은 2026-08-30 완료 Run E `DEV25_RESULTS_OPENAI_EXPERIMENTAL.xlsx`(SHA `4b301f4888ccdcdb8192285bdc0d586576350568931598920982c459e0732164`)이며, 공식 실행의 정체는 `model_name` 문자열이 아니라 사전등록 문서·실행 시점·원본 SHA256으로 확인한다.

### 한계 기록
사전등록 문서가 "이미 완료된 실행"을 공식으로 지정하는 동시에 이후 코드의 결과 파일명을 `DEV25_RESULTS.xlsx`로 명명해 문서 내부 모호성이 있었다. 2026-09-02 scoring contract 정정으로 Run E 우선 정의를 명시했다. Run O는 채점된 적이 없으므로 Run E/Run O 사이에서 점수에 따른 선택은 하지 않았다.
