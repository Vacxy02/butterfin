# 금융행동 사전검증 (Action Reversal)

2026-08-25에 팀의 실제 코드(`ai_rule.py`/`baseline_regex.py`/`blind25_fixed.py`, 박승렬
작성)를 전달받아 통합했습니다. 아래 세 파일은 **팀의 실제 코드 그대로**(이 세션에서 한
글자도 안 고침)이고, 그 외(`engine.py`/`rule_store.py`/`demo_rules.json`/`app.py`/
`wide_compiler.py` 등)는 팀 파일이 아직 없어서 이 세션이 구성한 것입니다.

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
                           #   있고 이 부분(넓은 스키마 추출)이 없어서 이 세션에서 새로 작성
  dev25_runner.py         # A(1회)/B(3회)/C(3회) = 175행 실행기
  blind25_samples.json    # CODEX_DEV25_v2.xlsx에서 추출한 25건 원문 (Gold 아님)
  scoring_contract.md      # 채점 필드 정의만 (Gold 없음)
tests/                   # 95개 단위 테스트 (전부 통과)
Dockerfile, render.yaml, fly.toml, requirements.txt, .env.example
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
# GEMINI_API_KEY 있으면 System B/C가 실제 Gemini 호출, 없으면 정직하게 accepted=N으로
# 채워짐(가짜 값을 지어내지 않음) — 로그에 어느 쪽인지 표시됨. 결과는
# ablation/DEV25_RESULTS.xlsx로 저장됨 (매번 재생성, 저장소에는 커밋 안 함)
```

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
3. **`wide_compiler.py`의 프롬프트가 팀이 실제로 쓰던 System B/C 프롬프트와 같은지
   확인.** 팀 실제 파일 3개(`ai_rule.py`/`baseline_regex.py`/`blind25_fixed.py`)에는
   System A와 Gate만 있고 System B/C 컴파일러가 없어서, 이 세션에서 스키마
   (`ExtendedRuleSchema`)와 Gate는 그대로 두고 프롬프트만 새로 썼습니다. 박승렬님께
   원래 프롬프트가 따로 있었는지 확인해서, 있으면 그걸로 교체해야 진짜 DEV25 실험
   조건이 됩니다.
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
