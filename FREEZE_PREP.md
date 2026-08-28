# Freeze 준비 기록 (Freeze 선언 아님)

박승렬 지시: "아직 Freeze 선언하는 건 아니고, 나중에 바로 고정할 수 있게 준비만
해두면 돼." 이 문서는 그 준비 기록이다 — **여기 적힌 걸로 Freeze가 선언된 게
아니다.** 실제 Freeze는 유료 API로 sanity rerun까지 끝난 뒤 박승렬이 선언한다.

기록 시각: 2026-08-28 (3차 갱신 — 박승렬의 "수학 고도화 추가팩"(11개 문서, Safe Zone
math v1.2)을 반영함. 2차 갱신은 프롬프트 원문/37행 원장 CSV/Evidence Bundle CSV 반영,
최초 기록은 2026-08-27). 이후 파일이 바뀌면 이 표는 최신이 아니게 되므로, Freeze
선언 직전에 아래 명령으로 다시 계산해서 갱신할 것.

## 1. 코드/데이터 SHA-256

| 구성요소 | 파일 | SHA-256 |
|---|---|---|
| Regex (System A) | `ablation/baseline_regex.py` | `ebfa0f299a466901a5f5dadec07adfdfce730a9105cce86168f18faa976a5470` |
| ai_rule.py (Rule Intelligence / Gate 기반) | `mvp/ai_rule.py` | `09edd477fc29d49c2c8dd1b3c5cadc2fe1573a8568a8ef6acc4c3ab7e091d84f` |
| Output schema + Gate (ExtendedRuleSchema/EvidenceGate) | `ablation/blind25_fixed.py` | `e4ffab1a50ffbf3c7be78652f5117e973da78f33388445fd15c37bb1322ff5f0` |
| Gemini wide-schema compiler (System B/C 호출부, **프롬프트 원문 반영 후 해시 변경**) | `ablation/wide_compiler.py` | `b7a30231d5423902d4aa2827beb3b8e3516216e45f1150b5f9727a50e1adce48` |
| DEV25 runner | `ablation/dev25_runner.py` | `fcdf7e180bc6ba1284bb5adea9c816a5ce90ef80de07561ab2c102e6e154b66c` |
| Deterministic engine (scoring/계산 로직, **Safe Zone v1.2 추가 후 해시 변경**) | `mvp/engine.py` | `c0973d322e422ab33f4dfae43beeaa155e50b57fd7de58c180f20fd2d4322002` |
| Rule store (**`known_institutions()` + `match()`에 product 파라미터/`known_products()` 추가로 해시 재변경**) | `mvp/rule_store.py` | `2af7c675be20e494cd5997627854af8ce52ccf65f469f0fcb5118112adb12b22` |
| 웹/API 엔트리포인트 (**Safe Zone API 스키마 배선 + `/api/health` institutions/products 목록 + `/api/evaluate` product 파라미터로 해시 재변경**) | `mvp/app.py` | `894835633678b74ad2daaa6f4e46c7c0cd885f20ec30ddc55bedca89fc7a99b3` |
| MVP 프론트 (**06_MVP_표시명세.md 12항목 재구성 + 은행/상품 선택 드롭다운(독립 2개) 추가로 해시 재변경**) | `mvp/static/index.html` | `81f1a20f9993e3f95e5066d892a93a45d83537d209a75af8ca4d3c79ce198764` |
| 공통 데이터 스키마 (**`TypedActionDelta.institution` + `.product` 필드 추가로 해시 재변경**) | `mvp/schemas.py` | `743e1f2969b2c6191e1e12da1703abb41699220f31b711939e8a381a11644aae` |
| 자연어 행동 해석기 (**은행명 감지 + 상품명 감지(독립) 로직 추가로 해시 재변경**) | `mvp/action_interpreter.py` | `ee0ee4eef33b34dbe659fc29d92fa98997a13fd8a4d84308c8bd1477b5501f20` |
| 배포용 규칙 8개 (**원장 재확인 3건 반영 후 해시 재변경**) | `mvp/demo_rules.json` | `aa58db204da101c3a3fb29cbc53dc08fc5a3824128d6efcaad870251c999eaa0` |
| **원장 원본 37행** (신규 확보) | `action_reversal_rule_ledger_v3.csv` | `f71ea7cc4b6b5d764a45aecdbbdffbf272165d23e1f65fca7f082765c2a3ca89` |
| **Evidence Bundle 보조 근거 CSV** (신규 확보) | `evidence_bundle_20260821.csv` | `5cd3f79f3ba9f5935f484c376e6ddb866e1afd07b85b4921659c89702754a214` |
| Dependency 목록 | `requirements.txt` | `d7522163b3fe5c6d85af7a2067d15773a9d49f71cc0998bc6bbb2850df015227` |
| Dockerfile (runtime) | `Dockerfile` | `59996b2395742035cbc14a4494c6ffced118f297cfe8245975c96e9b81eb52e0` |
| CHANGELOG (**MATH-V12-001 + FEAT-INSTITUTION-001 + FEAT-PRODUCT-001 추가로 해시 재변경**) | `CHANGELOG.md` | `1f0f4b441ec54aa8935b85b1ff45f1a71c08bc7ab814b9e3822a6de3e402378c` |
| Safe Zone v1.2 회귀테스트 (25개 필수 케이스) | `tests/test_safezone_v12.py` | `bb8b36c6f29873cad06982c903994e2cba71182ce8ae223b92a3cb5cf00c1463` |
| Action interpreter 회귀테스트 (**은행명 6개 + 상품명 8개 감지 케이스 추가로 해시 재변경, 총 22개**) | `tests/test_action_interpreter.py` | `f29d7d46b1e9564ba3c9746f18223513c5a04f6dcf5f4f03b3e5082d67c36073` |

재계산 명령:
```bash
python3 -c "
import hashlib
for f in ['ablation/baseline_regex.py','mvp/ai_rule.py','ablation/blind25_fixed.py',
          'ablation/wide_compiler.py','ablation/dev25_runner.py','mvp/engine.py',
          'mvp/rule_store.py','mvp/app.py','mvp/static/index.html','mvp/schemas.py',
          'mvp/action_interpreter.py','mvp/demo_rules.json',
          'action_reversal_rule_ledger_v3.csv','evidence_bundle_20260821.csv',
          'requirements.txt','Dockerfile','CHANGELOG.md','tests/test_safezone_v12.py',
          'tests/test_action_interpreter.py']:
    print(f, hashlib.sha256(open(f,'rb').read()).hexdigest())
"
```

### 은행/상품명 인식 기능 추가 (2026-08-28, 사용자 요청 → 사용자 지적으로 2차 보강)

문장에 "신협카드로 옮길 거야"처럼 특정 은행/상품명을 써도 그동안 무시되고 있던 걸
발견해서(사용자가 직접 질문해서 확인됨) 반영했다(`FEAT-INSTITUTION-001`). 이어서
사용자가 "은행명만으로 결정하면 안 되고 상품명을 봐야 한다"고 정확히 지적해서,
상품명도 은행명과 완전히 독립적인 축으로 감지·필터링하도록 보강했다
(`FEAT-PRODUCT-001`, 이유: 한 은행이 여러 상품을 취급하거나 같은 상품군을 여러
기관이 취급할 수 있어서 은행명 하나만으로는 부족함 — 원장 37행 기준 NH농협은행도
디딤돌대출을 취급). 상세는 `CHANGELOG.md` 참고. Freeze 준비 관점 핵심만: 두
경우 다 Gemini에게 추출을 맡기지 않고 `rule_store.known_institutions()`/
`known_products()`(실제 등록된 목록)와 대조하는 결정론적 키워드 매칭만 썼다 —
없는 이름을 지어내지 않는다는 원칙 유지. 회귀 테스트 총 14개 추가(은행명 6 +
상품명 8), 전체 재실행 **135 passed, 0 failed**. DEV25 A/B/C 파이프라인은
`TypedActionDelta`를 쓰지 않아(grep 재확인) 이번 변경과 완전히 무관하다.

### Safe Zone math v1.2 반영 (2026-08-28, 박승렬 "수학 고도화 추가팩" 11개 문서)

`ENGINE_VERSION = "engine_v1.2_safezone_2026-08-28"`(`mvp/engine.py`). 상세 내용/영향
범위/근거는 `CHANGELOG.md`의 `MATH-V12-001` 항목 참고. 여기서는 Freeze 준비 관점에서
핵심만 남긴다:

- 기존 함수는 전혀 수정하지 않고 `compute_safe_zone()`만 추가했다(순수 추가).
- 회귀테스트: 기존 95개 + 신규 26개(`tests/test_safezone_v12.py`, 04_신규_회귀테스트_
  명세.md의 25개 필수 케이스 전부 커버) = **121 passed, 0 failed** (전체 재실행 결과,
  2026-08-28).
- DEV25 A/B/C 추출 파이프라인(`ablation/dev25_runner.py`/`ablation/wide_compiler.py`/
  `mvp/schemas.py`)은 이 작업으로 전혀 건드리지 않았다 — grep으로 새 Safe Zone 필드명이
  그 파일들에 없음을 확인함(08_DEV25_보호규칙 §1 재확인 완료).
- `ablation/dev25_checkpoint.jsonl` 175행 전부 `http_status=null` — 이번 작업으로도
  Gemini 실호출은 여전히 0회(§3 재확인 완료).

### 배포 8규칙 ↔ 37행 원장 대조 결과 (2026-08-28 확정)

박승렬이 원장 CSV(37행)와 Evidence Bundle CSV를 보내와서 대조를 끝냈다. **8개 전부
원장 `rule_id`로 추적 가능하다** — 각 규칙의 `mvp/demo_rules.json`에 새로 추가한
`ledger_rule_ids` 필드가 그 매핑이다 (예: `KB_CARD_LOAN_STEP` 하나가 원장에서는
`_T1/_T2/_T3` 3행으로 나뉘어 있음). `source_url`도 전부 원장의 실제 URL로 교체했다
(전에는 "OO은행 상품페이지 > 우대금리" 같은 설명 텍스트였음).

최초 대조에서 값 불일치 3건이 나와 `demo_rules.json`에 `unverified_against_ledger`로
표시했는데, **같은 날(2026-08-28) 공식 페이지/원본 PDF를 직접 재조회해 세 값 전부
사실로 확인됐다** — 원장 자체가 해당 행을 아직 안 만들었을 뿐 값은 처음부터 맞았다.
각 규칙의 `ledger_reconfirmed_2026-08-28` 필드에 근거 원문을 남겼다:

1. **`HANA_HISTORY_SAVINGS.effect_pct_p = 4.70`** — 하나은행 공식 페이지에 원문
   그대로 있음("첫거래우대 연 4.70%"). 신규고객 특판 상품(기본 2.00%/최고 7.70%)이라
   다른 규칙보다 우대폭이 큰 게 정상. 원장이 이 행을 SENTINEL로만 다루며
   `effect_value`를 비워둔 게 원인 — 원장에 `effect_value=4.7` 보강 권장(부수 발견:
   원장의 `effect_kind`가 `rate_discount`인데 `rate_bonus`가 정합).
2. **`SHINHYUP_CARD_USAGE`의 하위 구간(4~7회 → 2.5%p)** — 신협 공식 페이지 본문에
   상위 구간(8회 이상 → 5.0%p)과 나란히 있음. 원장이 상위 구간만 정식 행으로 만들고
   하위 구간 행(`SHINHYUP_CARD_USAGE_T1`)을 아직 안 만든 상태.
3. **`HF_SUBSCRIPTION_DIDIMDOL.rate_floor_newlywed_pct = 1.2`** — 주금공 업무처리기준
   원본 PDF 17쪽에 원문 그대로 있음("생애최초 신혼가구인 경우...연 1.2% 적용"). 원장에
   아직 정식 행(`HF_RATE_FLOOR_NEWLYWED`)이 없는 상태.

**남은 실제 작업은 원장 CSV 쪽에 위 3개 행을 추가하는 것뿐** — 코드/데이터 쪽은
이미 정정 완료됐다(`ledger_rule_ids`에 신규 행 이름을 미리 반영해둠).

## 2. Gemini 호출 설정

| 항목 | 값 | 근거 |
|---|---|---|
| 모델 | `gemini-3.6-flash` (환경변수 `GEMINI_MODEL` 기본값) | `mvp/ai_rule.py` L66: `_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")` |
| temperature | `0.0` (재현성 우선, 금융 도메인이라 창의성 배제) | `mvp/ai_rule.py` L359 |
| top_p | 명시적으로 설정하지 않음 (SDK/모델 기본값 사용) | `mvp/ai_rule.py`의 `_call_gemini()`에 `top_p` 인자 없음 |
| System B/C 프롬프트 버전 | `wide_compiler.PROMPT_VERSION = "wide_compiler_v2_teamfrozen_2026-08-25_integrated_2026-08-28"` + 실행 시 해시 접미사(`_prompt_hash()`) | `ablation/wide_compiler.py` |
| Action Interpreter 프롬프트 버전 | `action_interpreter.PROMPT_VERSION = "action_interpreter_v1_2026-08-25"` | `mvp/action_interpreter.py` |

**2026-08-28 갱신**: 박승렬 회신으로 System B/C 프롬프트 원본을 확보했다 — 팀이
2026-08-25 "코드와 프롬프트를 확정(Freeze)했습니다" 메시지에서 고정한 것으로,
`wide_compiler._TEAM_FROZEN_SYSTEM_PROMPT`에 원문 그대로(한 글자도 안 고침) 들어가
있다. 이전에 이 세션이 임시로 새로 짰던 프롬프트는 이걸로 교체했다. 원문은 5개
행동 규칙만 정의하고(tiers 전부 추출/OR조건 정규화/exception 매핑/단위 포함 숫자
캡처/환각 금지) 14개 필드 이름 자체는 나열하지 않는데, response_schema가 필드
타입은 강제해도 필드별 의미까지는 안 알려주므로 그 부분은 이 세션이
`_FIELD_GUIDE`로 보충했다 — 원문과 보충분은 코드 안에 상수로 분리해뒀다.

**확인 완료**: `mvp/ai_rule.py` 안의 구형 `_COMPILE_PROMPT`(7필드 Rule Compiler용)는
`wide_compiler.py`/`dev25_runner.py` 어디서도 호출하지 않는다(grep으로 확인) —
박승렬이 감사에서 지적한 "구 프롬프트를 DEV25 B로 쓰면 안 됨" 조건은 이미 충족돼
있었다.

## 3. Runtime/의존성

- Python: `3.11.15` (이 세션 기준. 배포 환경/`Dockerfile`의 베이스 이미지 버전과 다를 수
  있으니 실제 배포 직전에 재확인할 것)
- 핵심 의존성 버전(`requirements.txt`에 고정): `Flask==3.1.3`, `pydantic==2.13.3`,
  `google-genai==2.19.0`, `openpyxl==3.1.5`
- `requirements.txt` 전체 해시는 위 표 참고.

## 4. Scoring / 채점 코드 — **미확정, 별도 자료 필요**

박승렬 회신에 따르면 이 저장소에는 아직 실제 "채점 코드"가 없다:

- `ablation/scoring_contract.md`는 채점 기준 **정의 문서**일 뿐 구현 코드가 아니다.
- `ablation/run_ablation.py`에 `score()` 함수가 있긴 하지만 **구정의 기준**(A=No-AI,
  B=Regex, C=Gemini)이라 지금 지시서(A=Regex, B=Gemini raw, C=Gemini+Gate) 기준과
  달라서 그대로 쓰면 안 된다 — 박승렬이 "재사용 금지"라고 명시.
- 새로 짜려면 박승렬이 언급한 `Claude_적대적감사_결과_2026-08-28.md`의 BLOCKER
  4가지(RUN_FAILURE는 전 필드 0.0으로 분모 25 포함 / 200+ERROR는 재시도 아닌 최종
  응답 / tiers는 MATERIAL만·구조는 STRUCTURAL만 / 채점 라벨 마스킹)를 반영해야
  하는데, **이 문서 자체를 아직 못 받았다** — 이게 있어야 정확하게 구현할 수 있다.

**필요한 것: `Claude_적대적감사_결과_2026-08-28.md` 파일.** 받으면 바로 scoring 코드
작성하고 이 표에 해시 추가하겠음.

## 5. Deploy commit

이 세션의 작업 디렉터리는 git 저장소가 아니라서(사용자의 실제 로컬 저장소가 별도로
있음) 여기서 commit hash를 기록할 수 없다. **Freeze 선언 직전, 실제 배포에 쓴 커밋에서
직접 기록할 것**:
```bash
git rev-parse HEAD          # 배포된 커밋 해시
git log -1 --format=%cI     # 커밋 시각
```
참고: 2026-08-28 기준 가장 최근 확인된 배포 커밋은 `97642dc`(DEV25 runner 개선/D-L-G
표시/에러 처리 정리) — 이번 회신 반영본은 아직 배포 전이므로 그 이후 새 커밋이 될 것.

## 6. 아직 채워지지 않은 항목

**유료 API로만 확정 가능:**
- Gemini 실제 응답 재현성 확인(E2E 반복) — 미실행
- DEV25 System B 25건 공식 실행 결과 — 미실행 (`GEMINI_API_KEY` 없어 B/C 전부 accepted=N)
- DEV25 System C(=B 재사용 + Gate) 25건 결과 — 미실행
- 위 결과에 따른 "일반 오류만 수정" 여부 — 대상 없음(아직 실행 전)

**추가 자료가 와야 확정 가능:**
- Scoring 코드 (`Claude_적대적감사_결과_2026-08-28.md` 필요, 위 4절 참고)

**팀(원장 관리자) 쪽에서 처리해야 할 것:**
- 원장 CSV에 `HANA_HISTORY_SAVINGS.effect_value=4.7`, `SHINHYUP_CARD_USAGE_T1`(4~7회
  →2.5pp), `HF_RATE_FLOOR_NEWLYWED`(1.2%) 3개 보강/신규 행 — 값은 이미 확인 끝났고
  원장에 반영만 하면 됨 (위 1절 참고)

**Safe Zone math v1.2(2026-08-28) 반영이 위 게이팅 상태를 바꾸지 않는다는 점 명시:**
수학 엔진 확장은 deterministic engine 뒤쪽 기능이라 DEV25 System B 공식 실행이나
Scoring 코드 여부와 무관하다(08_DEV25_보호규칙 §4 — 수학엔진 테스트 결과를 DEV25 AI
성능으로 표현 금지). `09_최종_self_audit_체크리스트.md`는 박승렬 지시대로 **이번
전달본에는 채우지 않았다** — DEV25 B/C 공식 실행 + 일반 오류 수정 + sanity rerun이
끝난 뒤 최종 zip에서만 채우기로 되어 있다.
