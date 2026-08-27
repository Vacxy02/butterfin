# Freeze 준비 기록 (Freeze 선언 아님)

박승렬 지시: "아직 Freeze 선언하는 건 아니고, 나중에 바로 고정할 수 있게 준비만
해두면 돼." 이 문서는 그 준비 기록이다 — **여기 적힌 걸로 Freeze가 선언된 게
아니다.** 실제 Freeze는 유료 API로 sanity rerun까지 끝난 뒤 박승렬이 선언한다.

기록 시각: 2026-08-27 (이 세션 기준. 이후 파일이 바뀌면 이 표는 최신이 아니게 되므로,
Freeze 선언 직전에 아래 명령으로 다시 계산해서 갱신할 것.)

## 1. 코드/데이터 SHA-256

| 구성요소 | 파일 | SHA-256 |
|---|---|---|
| Regex (System A) | `ablation/baseline_regex.py` | `ebfa0f299a466901a5f5dadec07adfdfce730a9105cce86168f18faa976a5470` |
| ai_rule.py (Rule Intelligence / Gate 기반) | `mvp/ai_rule.py` | `09edd477fc29d49c2c8dd1b3c5cadc2fe1573a8568a8ef6acc4c3ab7e091d84f` |
| Output schema + Gate (ExtendedRuleSchema/EvidenceGate) | `ablation/blind25_fixed.py` | `e4ffab1a50ffbf3c7be78652f5117e973da78f33388445fd15c37bb1322ff5f0` |
| Gemini wide-schema compiler (System B/C 호출부) | `ablation/wide_compiler.py` | `601d42fdc2323443f550d950122a9d9516fa7e8a5d9ea5d5d211375ec78d177f` |
| DEV25 runner | `ablation/dev25_runner.py` | `fcdf7e180bc6ba1284bb5adea9c816a5ce90ef80de07561ab2c102e6e154b66c` |
| Deterministic engine (scoring/계산 로직) | `mvp/engine.py` | `360c21306c1043db4d29230645ee249cacfebc579b056e93dc59ce026d5d5545` |
| Rule store | `mvp/rule_store.py` | `cd417eed4eb89b27398caa53770e95ef37b4df1d800f68a7bfb3dbd03ec10b59` |
| Rule ledger (배포용) | `mvp/demo_rules.json` | `90d12838cf19e84ca8879b745ea5f4092f6a47797305c57bfff530f77895c862` |
| Dependency 목록 | `requirements.txt` | `d7522163b3fe5c6d85af7a2067d15773a9d49f71cc0998bc6bbb2850df015227` |
| Dockerfile (runtime) | `Dockerfile` | `59996b2395742035cbc14a4494c6ffced118f297cfe8245975c96e9b81eb52e0` |

재계산 명령:
```bash
python3 -c "
import hashlib
for f in ['ablation/baseline_regex.py','mvp/ai_rule.py','ablation/blind25_fixed.py',
          'ablation/wide_compiler.py','ablation/dev25_runner.py','mvp/engine.py',
          'mvp/rule_store.py','mvp/demo_rules.json','requirements.txt','Dockerfile']:
    print(f, hashlib.sha256(open(f,'rb').read()).hexdigest())
"
```

**"rule ledger"에 대한 중요한 단서**: 위 표의 `mvp/demo_rules.json`(8개 규칙)은 박승렬이
말한 "최신 37행 원장"(`action_reversal_rule_ledger_v3.csv`)이 아니다. `demo_rules.json`의
`_meta.source`는 `공모전_Evidence Bundle.docx (2026-08-25 팀 최신본)`으로 기록돼 있고,
37행 원장 CSV 자체는 이 build/세션에 없어서 두 소스를 대조하지 못했다 (자세한 내용은
`README.md`의 "알려진 한계" 참고). Freeze 시점에 37행 원장이 확보되면 이 표에 그 파일의
해시도 별도로 추가하고, `demo_rules.json`과의 관계를 확정해야 한다.

## 2. Gemini 호출 설정

| 항목 | 값 | 근거 |
|---|---|---|
| 모델 | `gemini-3.6-flash` (환경변수 `GEMINI_MODEL` 기본값) | `mvp/ai_rule.py` L66: `_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")` |
| temperature | `0.0` (재현성 우선, 금융 도메인이라 창의성 배제) | `mvp/ai_rule.py` L359 |
| top_p | 명시적으로 설정하지 않음 (SDK/모델 기본값 사용) | `mvp/ai_rule.py`의 `_call_gemini()`에 `top_p` 인자 없음 |
| System B/C 프롬프트 버전 | `wide_compiler.PROMPT_VERSION = "wide_compiler_v1_2026-08-25"` + 실행 시 해시 접미사(`_prompt_hash()`, 프롬프트 원문 SHA-256 앞 12자) | `ablation/wide_compiler.py` |
| Action Interpreter 프롬프트 버전 | `action_interpreter.PROMPT_VERSION = "action_interpreter_v1_2026-08-25"` | `mvp/action_interpreter.py` |

**주의**: `wide_compiler.py`의 System B/C 프롬프트는 팀의 실제 파일 3개(`ai_rule.py`/
`baseline_regex.py`/`blind25_fixed.py`)에 System B/C용 프롬프트가 없어서 이 세션이 새로
작성한 것이다. 박승렬에게 원래 팀 프롬프트가 따로 있었는지 반드시 확인하고, 있다면
Freeze 전에 교체해야 한다 — 그래야 진짜 DEV25 실험 조건이 된다.

## 3. Runtime/의존성

- Python: `3.11.15` (이 세션 기준. 배포 환경/`Dockerfile`의 베이스 이미지 버전과 다를 수
  있으니 실제 배포 직전에 재확인할 것)
- 핵심 의존성 버전(`requirements.txt`에 고정): `Flask==3.1.3`, `pydantic==2.13.3`,
  `google-genai==2.19.0`, `openpyxl==3.1.5`
- `requirements.txt` 전체 해시는 위 표 참고.

## 4. Scoring / 채점 코드

- 이 저장소에는 실제 "채점 코드"가 없다 — `ablation/scoring_contract.md`는 **채점 기준
  정의 문서일 뿐**(Field Match/Exception Recall/Attribution Recall/Complex Structure
  Accuracy/Evidence Grounding/Dangerous Error Rate/Executable Rule Rate 7개 지표 정의),
  실제 채점(Gold 대조)은 별도 담당자가 수행한다고 그 문서 자체에 명시돼 있다.
  `DO_NOT_ADD_GOLD.txt` 제약에 따라 이 세션은 Gold를 보지도, 채점 코드를 만들지도
  않았다. Freeze 대상에 "scoring code"를 넣어야 한다면 그 채점 코드가 어디 있는지
  박승렬에게 먼저 확인이 필요하다.

## 5. Deploy commit

이 세션의 작업 디렉터리는 git 저장소가 아니라서(사용자의 실제 로컬 저장소가 별도로
있음) 여기서 commit hash를 기록할 수 없다. **Freeze 선언 직전, 실제 배포에 쓴 커밋에서
직접 기록할 것**:
```bash
git rev-parse HEAD          # 배포된 커밋 해시
git log -1 --format=%cI     # 커밋 시각
```

## 6. 아직 채워지지 않은 항목 (유료 API로만 확정 가능)

- Gemini 실제 응답 재현성 확인(E2E 반복) — 미실행
- DEV25 System B 25건 공식 실행 결과 — 미실행 (`GEMINI_API_KEY` 없어 B/C 전부 accepted=N)
- DEV25 System C(=B 재사용 + Gate) 25건 결과 — 미실행
- 위 결과에 따른 "일반 오류만 수정" 여부 — 대상 없음(아직 실행 전)

이 문서는 이 세션이 대신 채울 수 없는 위 6개 항목을 제외한 나머지를 전부 기록했다.
