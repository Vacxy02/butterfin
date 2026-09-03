# DEV25 / FINAL_UNSEEN 채점 — canonical 문서 안내 (2026-08-31 개정)

**이 문서는 채점 기준을 재정의하지 않는다.** 이전 버전(16필드 표기, "Field/Exact Rule
Match" 등)은 DEV25 v1.1 LOCK 평가규칙과 표기가 어긋나 있어 폐기한다. 지금부터는 이 문서가
채점 수식의 출처가 아니라, **어디가 진짜 출처인지 가리키는 짧은 참조문서**다.

## Canonical scoring contract

**DEV25 v1.1 LOCK 평가규칙 + 박승렬 측 `dev25_scoring_v11.py` — PATCHED 2026-08-31가
채점 계산의 유일한 authoritative source다.** 2026-08-31에 실제 파일을 전달받아
`ablation/dev25_scoring_v11.py`로 이 리포지토리에도 추가했다(참고/구조 대조용 — 이
리포지토리는 채점 수식을 독자적으로 다시 정의하거나 추정하지 않는다). `dev25_runner.py`가
만드는 `DEV25_RESULTS*.xlsx`의 "DEV25_RESULTS" 시트를 이 스크립트가 그대로 읽을 수 있음을
mock 실행으로 구조 검증했다(sample_id/system/run_id/accepted/schema_valid 컬럼 매칭 확인,
Gold 없이 구조만 검증 — 실제 채점 수치는 만들지 않았다).

**2026-08-31 PATCHED 갱신**: 같은 날 승렬 측이 패치된 버전(`dev25_scoring_v11.py —
PATCHED 2026-08-31`)을 다시 전달해서 그대로 덮어썼다(수식/로직은 이 리포지토리가 손대지
않음, 파일 통째로 교체). PATCHED 버전이 이전 버전 대비 고친 것(파일 자체의 docstring
그대로 옮김):

1. Clean Retention Rate를 v1.1 §7-10 정의대로 정확히 구현.
2. C(엔진 통과분, accepted=Y)에 대한 Safe Precision Proxy 구현.
3. Hallucinated Material Rate를 자유 텍스트 키워드가 아니라 전용 블라인드 GROUNDING
   시트 기준으로 계산.
4. RUN_FAILURE가 accepted=N / schema_valid=False / JSON 파싱 실패를 명시적으로 처리.
5. Coverage가 v1.1 분모를 그대로 보고하고, A가 schema_valid를 안 남겼으면 공식
   schema coverage가 아니라고 표시.
6. M-5 B-2 민감도 분석: 공식 Gold는 그대로 두고 U001/U002/U004/U013 제외는 민감도
   참고용으로만 보고(공식 지표 대체 아님).
7. 0.5점은 반드시 서술 근거가 있어야 함.

필수 지표(이름만 여기 기록 — 계산 방식은 `dev25_scoring_v11.py` 기준):

- Schema Valid Rate
- Gold Field Recall
- Exact Material Accuracy
- Structural Recall
- Hallucinated Material Rate
- WRS
- Unweighted Field Score
- Coverage
- Safe Precision Proxy
- Clean Retention Rate

## Gold 정책 및 채점 담당 (2026-08-31 현재 운영 기준으로 갱신)

Gold 정답은 이 폴더에 없고, 앞으로도 넣지 않는다 — 이 원칙 자체는 이전 버전 문서와
동일하게 유지된다. 채점 실행 주체는 현재 운영 기준으로 다음과 같이 역할이 나뉜다:

- **새미 — 공식 독립 블라인드 채점자.** Gold를 보유하고 `dev25_scoring_v11.py —
  PATCHED 2026-08-31`로 실제 채점을 수행하는 주체. 이 리포지토리는 그 채점 수식/코드를
  독자적으로 다시 정의하거나 추정하지 않는다(위 "Canonical scoring contract" 절 그대로).
- **승렬 — 봉인키 관리 / 비블라인드 교차확인.** `sealed_key.csv`(출력 코드 → system/run_id
  매핑) 등 봉인 키 관리를 맡고, 새미의 블라인드 채점 결과를 비블라인드로 교차확인한다.

이 리포지토리는 어느 쪽 채점 로직에도 관여하지 않는다 — 위 역할 구분은 문서 표현
정정일 뿐, `dev25_scoring_v11.py`의 계산 코드는 이번 갱신으로 전혀 손대지 않았다.

## 이 리포지토리가 채점 파이프라인에 제공하는 것

`ablation/dev25_runner.py`가 만드는 `dev25_checkpoint_<provider>.jsonl` / `DEV25_RESULTS*.xlsx`
행마다 다음 컬럼이 채워진다 — `dev25_scoring_v11.py`가 그대로 입력으로 소비할 수 있도록
이 구조를 고정 계약으로 유지한다:

```
sample_id, system, run_id, model_name, prompt_version,
raw_output_json, parsed_output_json, schema_valid,
accepted, reject_reason, http_status, retry_count,
latency_ms, error_log, reused_from_run
```

- `system`: `A`(regex baseline, 1회) / `B`(Gemini 또는 GPT 넓은 스키마 추출, Gate 없음,
  3회) / `C`(B 결과 재사용 + Gate만 적용, API 재호출 없음, 3회) — `reused_from_run`으로
  C가 어느 B 실행을 재사용했는지 추적 가능.
- `accepted`/`reject_reason`: `EVAL_STRICT=1`(공식 평가모드)로 돌렸을 때는
  `reject_reason`이 `"RUN_FAILURE (EVAL_STRICT): ..."` 형태로 명시된다 — live 실패가
  과거 cache로 조용히 대체되지 않고 실패로 남았다는 뜻이며, 채점 시 이 행은 "값이
  없어서 낮은 점수"가 아니라 "이번 실행에서 API가 실패했다"로 별도 집계해야 한다.
- **공식 DEV25 블라인드 재채점 대상은 `docs/PROVIDER_GPT_OFFICIAL.md`(2026-08-31)가
  지정한 "이미 완료된 DEV25 25×3 GPT 실행", 즉 2026-08-30 완료 실행
  `DEV25_RESULTS_OPENAI_EXPERIMENTAL.xlsx`
  (SHA256 `4b301f4888ccdcdb8192285bdc0d586576350568931598920982c459e0732164`,
  파일 생성 2026-08-30 16:24 KST)이다.**
  해당 실행파일의 `model_name` 필드는 8/31 이전 코드에서 생성된 과거 표기
  "gpt-4o-mini (GPT 실험용 — 비공식, 공식 Gemini 결과 아님)"을 유지하고 있으나,
  이는 결과 재생성 금지 원칙에 따라 원본 실행물을 보존했기 때문이다.
  **공식 실행의 정체성은 `model_name` 문자열이 아니라 사전등록 문서, 실행 시점,
  원본 파일 SHA256으로 확인한다.**
  8/31 이후 코드가 생성하는 `model_name` "… (DEV25 공식 System B — GPT, 2026-08-31 확정)"은
  provider 명칭 정합화의 결과일 뿐, 그 문자열이 찍힌 파일이 자동으로 공식 대상이 되는
  것은 아니다. 8/31 이후 생성된 별도 실행(예: `DEV25_RESULTS.xlsx`, SHA256
  `9e4bd6eb764a76641168e9802a78571532da046645600d9c826c65f663c3d5d6`)은 출처
  증거(실행자·시각·EVAL_STRICT·run_metadata·checkpoint)가 확보된 경우에만
  "재현성 reference run"으로 기록하며 공식 점수 산출에는 사용하지 않는다.
  DEV25는 development benchmark로 계속 유지되며 FINAL_UNSEEN 성능처럼 표현하지 않는다.
  `model_name`에 Gemini 모델명(예: gemini-...)만 찍힌 행은 참고(reference) 실행이다.

## 기관별로 쪼개서 봐야 하는 이유 (기존 내용 유지)

2026-08-25 작업보고에 기록된 대로 BLIND25 25건 중 IBK 8건(그중 5건이 사실상 같은
상품의 변형)·카카오뱅크 6건이 56%를 차지한다. 총점만 보면 이 두 기관 형식이 결과를
크게 좌우하므로, 채점자는 기관별/archetype별로 나눠서 봐야 한다.

## 이 세션에서 한 것 — 채점이 아니라 파이프라인 검증 (기존 내용 유지)

`dev25_runner.py`를 mock 모드로 실행해 175행이 기계적으로 만들어지는지, 스키마가
깨지지 않는지, Gate가 실제로 동작하는지(조작된 값 차단)만 확인했다. **이건 Gold 채점이
아니다** — 실제 채점은 별도 담당자가 Gold를 가지고 위 지표대로 진행해야 한다.

## 이 문서의 변경 이력

- 2026-08-25: 최초 작성 (16필드, Field/Exact Rule Match 등 구정의).
- 2026-08-31: 구정의가 DEV25 v1.1 LOCK 평가규칙과 불일치함이 확인되어, 이 문서를
  "채점 기준 정의 문서"에서 "canonical 출처(`dev25_scoring_v11.py`) 안내 + 이
  리포지토리의 출력 계약 문서"로 성격을 바꿔 교체함. 수식 자체는 여기서 다시
  만들지 않음 — 임의 재정의가 대조 불가능한 새 scorer를 낳는 위험을 피하기 위함
  (박승렬 지시).
- 2026-08-31 (같은 날, 후속): canonical scorer가 `dev25_scoring_v11.py — PATCHED
  2026-08-31`로 교체됨을 명시. 이 리포지토리는 파일을 그대로 덮어썼을 뿐 채점 로직을
  독자적으로 수정하지 않음(동학 지시 — "새로 구현하거나 scoring 로직 수정하지 말 것").
- 2026-08-31 (같은 날, Freeze 직전 최종 정리): "Gold 정책" 절의 채점 담당자 표현을
  현재 운영 기준으로 정정 — 새미(공식 독립 블라인드 채점자)/승렬(봉인키 관리·비블라인드
  교차확인)로 역할 명시. 채점 수식/`dev25_scoring_v11.py` 코드는 이번 정정으로 전혀
  손대지 않음(동학 지시).
- 2026-09-02: "공식 블라인드 재채점 대상" 정의를 model_name 문자열 기준에서
  사전등록 문서(PROVIDER_GPT_OFFICIAL.md 2026-08-31)·실행 시점·원본 파일 SHA256 기준으로
  정정. 대상 = 2026-08-30 완료 실행 DEV25_RESULTS_OPENAI_EXPERIMENTAL.xlsx
  (SHA 4b301f48…). 8/31 이후 별도 실행(DEV25_RESULTS.xlsx, SHA 9e4bd6eb…)은 출처 확인
  전까지 UNVERIFIED REFERENCE. 실험 정의·수식·코드·Gold 변경 없음 — 표현 정정(승렬 감사
  09-02, 신원 승인).
