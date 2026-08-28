# 금융행동 사전검증 (Action Reversal)

2026-08-25에 팀의 실제 코드(`ai_rule.py`/`baseline_regex.py`/`blind25_fixed.py`, 박승렬
작성)를 전달받아 통합했습니다. 아래 세 파일은 **팀의 실제 코드 그대로**(이 세션에서 한
글자도 안 고침)이고, 그 외(`engine.py`/`rule_store.py`/`demo_rules.json`/`app.py`/
`wide_compiler.py` 등)는 팀 파일이 아직 없어서 이 세션이 구성한 것입니다.

2026-08-27: 박승렬의 체크리스트(유료 API 오기 전 준비 작업)를 반영했습니다 —
① DEV25 runner에서 System C가 Gemini를 다시 부르지 않고 System B의 결과를 재사용,
② cache/checkpoint(`dev25_checkpoint.jsonl`) + 429/5xx/timeout 재시도 정책,
③ 결과 화면에 D/L/G(실제 원 금액)·Action Reversal 여부 표시,
④ 공개 화면에서 `AR_MODE=DEMO` 문구/내부 에러 노출 제거 + fail-closed 처리,
⑤ Evidence 링크 클릭 가능화(실제 URL이 있을 때만),
⑥ 배포 규칙 8개와 37행 원장의 연결 여부 확인,
⑦ Freeze 대비 버전/해시 기록(`FREEZE_PREP.md`). 자세한 내용은 각 절 참고.

## 구조

```
mvp/
  app.py                # Flask 웹/API (/, /api/health, /api/interpret, /api/evaluate)
  action_interpreter.py # 자연어 → TypedActionDelta (Gemini live + mock, 라이브 데모용)
  schemas.py             # TypedActionDelta (action_interpreter 출력 타입)
  ai_rule.py              # ★팀 실제 코드★ Rule Intelligence Layer (의미유의성·규칙컴파일·
                           #   8게이트 환각 방어, google.genai SDK + 캐시)
  engine.py               # deterministic 계산 (G=D+L, Safe Limit, TTB, TTR, decide)
  rule_store.py            # demo_rules.json 로딩/매칭
  demo_rules.json          # 검증된 규칙 8개 (Evidence Bundle 기반, 5개 금융사)
  gemini_client.py          # Gemini REST 호출 공통 (action_interpreter.py 전용)
  make_bundle.py            # 빌드시점 자가진단 (Docker RUN에서 실행됨)
  verify_deploy.py          # 배포 후 실측 검증 스크립트
ablation/
  baseline_regex.py     # ★팀 실제 코드★ System A — 강한 Regex baseline (v5)
  blind25_fixed.py       # ★팀 실제 코드★ ExtendedRuleSchema(14필드) + EvidenceGate
  wide_compiler.py        # System B/C용 Gemini 컴파일러 — ai_rule.py의 실제 호출/캐시
                           #   경로(ai_rule._invoke)를 재사용. 팀 파일에는 System A/Gate만
                           #   있고 이 부분(넓은 스키마 추출)이 없어서 이 세션에서 새로 작성.
                           #   compile_raw()=System B(Gemini 호출), gate_only()=System C
                           #   (Gemini 재호출 없이 B의 결과에 Gate만 적용)
  dev25_runner.py         # A(1회)/B(3회)/C(3회) = 175행 실행기. C는 B의 3회 결과를
                           #   그대로 재사용(_row_from_c)하고 Gemini를 다시 부르지 않음.
                           #   dev25_checkpoint.jsonl에 문항 단위로 체크포인트 저장 —
                           #   중간에 API 오류가 나도 재실행 시 이어서 돈다
                           #   (`python dev25_runner.py --fresh`로 처음부터 새로 가능)
  blind25_samples.json    # CODEX_DEV25_v2.xlsx에서 추출한 25건 원문 (Gold 아님)
  scoring_contract.md      # 채점 필드 정의만 (Gold 없음)
tests/                   # 95개 단위 테스트 (전부 통과)
FREEZE_PREP.md            # Freeze 대상 파일들의 현재 버전/SHA256 기록 (Freeze 선언 아님, 준비만)
action_reversal_rule_ledger_v3.csv  # 박승렬 제공, 37행 원장 원본 (2026-08-28 확보)
evidence_bundle_20260821.csv        # 박승렬 제공, 원장 보조 근거(evidence_span/locator) CSV
Dockerfile, render.yaml, fly.toml, requirements.txt, .env.example, .gitignore
```

## 로컬 실행

```bash
pip install -r requirements.txt
cd mvp
python make_bundle.py        # 자가진단 4/4 통과 확인
AR_MODE=DEMO python app.py   # http://localhost:8000
```

`GEMINI_API_KEY`를 환경변수로 주면 실제 Gemini를 쓰고, 없으면 action_interpreter는
mock으로, DEV25 System B/C는 정직하게 accepted=N(추출 실패)으로 동작합니다.

## 테스트

```bash
for f in tests/*.py; do AR_ROOT=$(pwd) python3 "$f"; done
```

95개 전부 통과 (engine 22, ai_rule 23, baseline_regex 30, action_interpreter 8,
dev25_runner 12).

## DEV25 실행 (실제 또는 키 없음)

```bash
AR_ROOT=$(pwd) python ablation/dev25_runner.py
# GEMINI_API_KEY 있으면 System B가 실제 Gemini 호출, 없으면 정직하게 accepted=N으로
# 채워짐(가짜 값을 지어내지 않음) — 로그에 어느 쪽인지 표시됨. System C는 Gemini를
# 다시 부르지 않고 System B의 3회 결과를 그대로 재사용해 Evidence/Schema Gate만
# 적용함. 결과는 ablation/DEV25_RESULTS.xlsx로 저장됨(매번 재생성, 커밋 안 함).
#
# 중간에 API 오류가 나서 죽어도 그냥 같은 명령을 다시 실행하면 이어서 돈다 —
# ablation/dev25_checkpoint.jsonl에 문항×System×run 단위로 이미 끝난 결과가
# 저장돼 있어서 처음부터 다시 돌 필요가 없다. 완전히 새로 돌리려면:
AR_ROOT=$(pwd) python ablation/dev25_runner.py --fresh
```

결과 행마다 다음 필드가 남는다: `sample_id, system, run_id, model_name, prompt_version,
raw_output_json, parsed_output_json, schema_valid, accepted, reject_reason, http_status,
retry_count, latency_ms, error_log, reused_from_run`. `reused_from_run`은 System C 행에만
채워지며 "이 C 행이 어느 B 실행 결과를 재사용했는지"를 감사 추적하는 용도다(C 행은
`http_status=None, retry_count=0` — Gemini를 호출한 적이 없다는 뜻). 재시도는
429/5xx/timeout일 때만 하고(`wide_compiler._is_retryable`), 유효한 응답이 한 번 나오면
그대로 최종값으로 쓴다 — "답이 마음에 안 든다"는 이유의 재시도는 코드 어디에도 없다.

## Docker / 배포

```bash
docker build -t action-reversal .
docker run -e AR_MODE=DEMO -e GEMINI_API_KEY=<키> -e GEMINI_MODEL=gemini-3.6-flash -p 8000:8000 action-reversal
```

`render.yaml`(1순위, 싱가포르) 또는 `fly.toml`(2순위, 도쿄) 참고. 반드시 "항상 켜짐" 플랜을
쓰세요 — 무접속 시 슬립되는 무료 플랜은 심사에서 흰 화면 위험이 있습니다. `GEMINI_API_KEY`는
코드에 넣지 말고 배포 플랫폼 대시보드 환경변수로만 설정하세요.

배포 후:
```bash
python mvp/verify_deploy.py https://발급받은주소
```

## 박승렬 체크리스트 진행 상황 (2026-08-27)

**API 키 오기 전 (완료):** DEV25 runner(C가 B 재사용/cache-checkpoint/429·5xx·timeout만
재시도) · D/L/G+Action Reversal 화면 표시 · AR_MODE=DEMO/None/내부에러 제거 ·
fail-closed 처리 · Evidence 링크(있는 것만) · 37행 원장 연결 확인(위 "알려진 한계" 참고,
연결 불가 확인됨) · `FREEZE_PREP.md`(버전/해시 기록, Freeze 선언 아님).

**유료 API 확보 후 (아직 미착수 — 이 세션에서 하지 않음):** Gemini E2E 반복 확인 →
DEV25 B 25건 공식 실행 → C 실행(Gemini 재호출 0회, 이미 구조는 준비됨) → 전체
로그/결과 박승렬에게 전달 → (문제 있으면) 파서/프롬프트/schema/Gate 일반 오류만 수정 →
sanity rerun → Freeze 준비 완료 보고. **Freeze 전에는 FINAL_UNSEEN 문제/Gold를 보지
않습니다.**

**2026-08-28 박승렬 회신 후 진행 상황:** 프롬프트 원본 반영, 37행 원장 대조,
Evidence URL 실링크 반영 — 3건 다 완료(`FREEZE_PREP.md` 1~2절 참고). **Scoring 코드는
아직 미착수** — `Claude_적대적감사_결과_2026-08-28.md`(BLOCKER 4가지가 적힌 감사
문서)를 받아야 정확히 구현할 수 있어서, 이 파일을 박승렬에게 요청해야 합니다.

## 지금부터 실제로 해야 할 일 (우선순위 순)

이 세션이 대신 할 수 없는 것들만 남았습니다.

1. **`docker build -t action-reversal .` 로컬에서 직접 한 번.** 이 세션엔 Docker 데몬이
   없어서 못 돌려봤습니다 — 대신 `make_bundle.py`/`gunicorn` 등 Dockerfile 안의 개별
   명령은 전부 직접 실행해 성공을 확인했습니다. 이번에 `make_bundle.py`의 실제 버그
   (존재하지 않는 옛 `ai_rule` API를 부르고 있어서 빌드가 100% 실패했을 것)와
   `requirements.txt` 누락 의존성(`pydantic`, `google-genai`)을 고쳤으니, 지금 시점
   기준으로는 빌드가 될 겁니다 — 그래도 실제로 한 번 돌려서 확인해주세요.
2. **`GEMINI_API_KEY` 발급 → 로컬에서 실제 Gemini 응답 확인.** 지금까지 이 환경엔 키가
   없어서 action_interpreter는 mock, DEV25 System B/C는 전부 accepted=N(정직한 실패)
   상태입니다.
3. **(2026-08-28 해결됨) `wide_compiler.py` 프롬프트를 팀 원본으로 교체 완료.**
   박승렬 회신으로 2026-08-25에 팀이 실제로 Freeze한 System B 프롬프트 원문을
   받아서 `wide_compiler._TEAM_FROZEN_SYSTEM_PROMPT`에 그대로(한 글자도 안 고침)
   반영했습니다. 원문이 14개 필드 이름까지는 나열하지 않아서, 필드별 의미 설명은
   이 세션이 `_FIELD_GUIDE`로 보충했고 코드에서 원문과 명확히 구분해뒀습니다.
4. **진짜 `GEMINI_API_KEY`로 DEV25 재실행 → Freeze.** Freeze 시 기록할 것: 위 세 실제
   코드 파일의 SHA-256, `wide_compiler.PROMPT_VERSION`, Gemini model/설정.
5. **Render 또는 Fly.io에 배포 → `verify_deploy.py`로 실측.**
6. **FINAL_UNSEEN** (Freeze 이후): 개발자(이동학)가 안 본 새 약관 20~25건 별도 수집 →
   Gold 비공개 작성 → `dev25_runner.py`와 동일 구조로 한 번만 실행. 실행 중 코드/prompt
   수정 금지.

## 알려진 한계 (정직하게 남김)

- **규칙이 8개뿐**(`mvp/demo_rules.json`, Evidence Bundle 18개 중 4가지 action_type
  대표 사례 위주). 팀의 실제 규칙 저장소가 따로 있다면 그쪽을 우선하세요.
- **institution 없이 여러 규칙이 매칭되면 첫 번째를 씁니다.** 실서비스라면 사용자가
  상품을 고르게 하거나 REVIEW로 보내야 합니다.
- **`baseline_regex`(v5, 팀 실제 파일)는 계단형 tier 감지가 약합니다** — `parse_tiers()`는
  금액 수와 우대폭 수가 정확히 같을 때만 구간을 나눕니다. 팀 자체 docstring에 "이게 이
  기준선의 한계이고 그 한계가 실험의 논점"이라 적혀 있어 일부러 안 고쳤습니다.
- **`decide()`의 HOLD/REVIEW 경계**는 `PROJECT_CURRENT_STATE.md` §3("시간 하나만으로
  나누지 않는다")를 해석해 새로 설계했습니다(engine.py는 팀 실제 파일이 아직 없음).
  TTR 확인되면(몇 개월 뒤든) HOLD, TTB만 있고 TTR 없으면 REVIEW. 팀의 실제 구현이 있다면
  대조해서 `engine.py`만 고치면 됩니다.
- **NPV/할인율 계산이 없습니다.**
- **(2026-08-28 해결됨) 배포 규칙 8개 ↔ 37행 원장 대조 완료, 값 불일치 3건도 전부 재확인 완료.**
  박승렬이 원장 CSV(`action_reversal_rule_ledger_v3.csv`, 37행)와 보조 근거 CSV
  (`evidence_bundle_20260821.csv`)를 보내와서 대조했습니다. **8개 전부 원장
  `rule_id`로 추적됩니다** — `mvp/demo_rules.json`의 각 규칙에 `ledger_rule_ids`
  필드로 매핑을 남겼습니다(예: `KB_CARD_LOAN_STEP` 하나 = 원장의 `_T1/_T2/_T3` 3행).
  최초 대조에서 3건(`HANA_HISTORY_SAVINGS.effect_pct_p=4.70`,
  `SHINHYUP_CARD_USAGE`의 4~7회 구간, `HF_SUBSCRIPTION_DIDIMDOL` 신혼부부 금리하한
  1.2%)이 원장/근거 CSV에 안 보여서 `unverified_against_ledger`로 표시했는데, 같은
  날 공식 페이지/원본 PDF를 직접 재조회해 **세 값 전부 사실로 확인**됐습니다 — 원장
  자체가 해당 3개 행을 아직 안 만들었을 뿐 값은 처음부터 맞았습니다. 각 규칙의
  `ledger_reconfirmed_2026-08-28` 필드에 근거 원문을 남겼습니다. 자세한 내용은
  `FREEZE_PREP.md` 1절 참고.
- **(2026-08-28 해결됨) Evidence 링크가 실제 URL로 채워졌습니다.** 원장 CSV의
  `source_url` 열에 37/37 전부 실제 `https://` 링크가 있어서, `mvp/demo_rules.json`
  8개 규칙의 `source_url`을 전부 그 값으로 교체했습니다. `mvp/static/index.html`이
  `http(s)://`로 시작하는 URL을 클릭 가능한 링크로 렌더링하므로 이제 실제로 클릭됩니다.
- **Action Reversal 여부는 `direct_benefit_monthly`(이 행동으로 즉시 얻는 이득, 예:
  카드 캐시백) 입력값에 좌우됩니다.** `Reversal := D_T>0 and G_T<0`이라는 팀의 엄격한
  정의상, 이 값을 0으로 두면(입력 안 하면) D=0이라 조건을 만족하지 못해 손실이 있어도
  `action_reversal=false`로 나옵니다 — "당장은 이득인데 전체로는 손해"를 가리는 지표이지
  "손해가 있는지"를 가리는 지표가 아니기 때문입니다. UI에 이 값을 입력하는 필드를
  새로 추가해뒀습니다(2번 카드, "즉시 얻는 이득").
