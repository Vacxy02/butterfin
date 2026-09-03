"""DEV25 System B/C 추출 모듈(mvp/ai_rule.py, 박승렬 작성)에 추가한
AI_PROVIDER(Gemini/GPT) 스위치 회귀테스트 (2026-08-30 추가).

배경: tests/test_openai_provider.py는 "라이브 데모"(mvp/action_interpreter.py)
쪽 스위치를 검증한다. 이 파일은 그와 별개로 **DEV25 공식 채점 경로**인
mvp/ai_rule.py 자체에 넣은 AI_PROVIDER 스위치를 검증한다 — 처음엔(2026-08-30)
"GPT로 돌리면 어떻게 나오는지 실험만 해보고 싶다"는 요청으로 추가되어 "실험용/
비공식"으로 표시됐지만, 2026-08-31 박승렬 지시로 **이번 대회 공식 System B
provider가 GPT로 확정**됐다 — 이 파일의 assertion도 그 확정에 맞춰 갱신한다
(라벨 문구만 "실험용"→"공식"으로 바뀌었을 뿐, 아래 안전장치 자체는 그대로다).

이 파일이 반드시 지켜야 한다고 확인하는 안전장치 3가지:
  1. AI_PROVIDER를 아무도 안 건드리면(기본값 "gemini") ai_rule.py의 기존 동작이
     한 글자도 안 바뀐다 — _MODEL/api_key_present()/live_status() 같은 "공식
     준비 상태" 함수는 여전히 GEMINI_API_KEY만 본다(이 함수들은 DEV25 provider
     확정과 무관한 범용 함수라서 안 건드림).
  2. AI_PROVIDER=openai로 캐시를 쓰면 파일명 네임스페이스가 분리되어(_cache_path)
     Gemini 캐시와 절대 섞이지 않는다.
  3. AI_PROVIDER=openai로 결과를 만들면 model 라벨(_active_model_name)과
     dev25_runner의 출력(모델명 컬럼, mock 여부 안내, 산출 파일명)이 전부
     "어느 provider가 실제로 호출됐는지"를 명확히 구분해서 표시한다(2026-08-31
     이전엔 "GPT 실험용", 이후엔 "DEV25 공식 System B" 문구로 구분).

기존 168개 테스트(action_interpreter 22 + ai_rule 23 + baseline_regex 30 +
dev25_runner 12 + engine 22 + safezone_v12 26 + fix4_safezone 24 +
openai_provider 9)는 이 파일에서 한 줄도 건드리지 않는다 — 순수 추가(additive)다.

주의: 이 회귀테스트는 08_DEV25_보호규칙의 "DEV25 파일은 새 세션 심볼을 참조하지
않아야 한다"는 일반 원칙과는 다른 상황을 검증한다 — 이번 라운드는 동학이 그
파일(ai_rule.py) 자체를 실험적으로 확장하는 것을 명시적으로 승인했기 때문에,
여기서 확인하는 것은 "안 건드렸는지"가 아니라 "건드렸어도 공식 경로가 안전하게
격리되는지"다.
"""
import importlib
import os
import subprocess
import sys

MVP_DIR = os.path.join(os.path.dirname(__file__), "..", "mvp")
ABLATION_DIR = os.path.join(os.path.dirname(__file__), "..", "ablation")
sys.path.insert(0, MVP_DIR)
sys.path.insert(0, ABLATION_DIR)

passed = failed = 0


def check(name, cond, detail=None):
    global passed, failed
    if cond:
        print(f"✅ {name}")
        passed += 1
    else:
        print(f"❌ {name}" + (f" — {detail}" if detail is not None else ""))
        failed += 1


def run_in_subprocess(code: str, env_overrides: dict, cwd: str = MVP_DIR) -> str:
    """AI_PROVIDER는 모듈 로드 시점 상수라 같은 프로세스에서 os.environ만 바꿔서는
    재적용되지 않는다 — 실제 배포(env var 설정 후 프로세스 기동)와 같은 조건으로
    검증하려면 매번 새 프로세스를 띄워야 한다."""
    env = {k: v for k, v in os.environ.items()
            if k not in ("AI_PROVIDER", "OPENAI_API_KEY", "GEMINI_API_KEY")}
    env.update(env_overrides)
    out = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, f"subprocess failed: stdout={out.stdout!r} stderr={out.stderr!r}"
    return out.stdout.strip()


# ---------------------------------------------------------------------------
# 1. 기본값(AI_PROVIDER 미설정) → ai_rule.py의 "공식 준비 상태" 함수는 완전히
#    기존과 동일 — GPT 스위치를 넣었다고 해서 한 글자도 안 바뀐다.
# ---------------------------------------------------------------------------
code_default = (
    "import ai_rule;"
    "print(ai_rule.AI_PROVIDER);"
    "print(ai_rule._active_model_name() == ai_rule._MODEL);"
    "print(ai_rule._active_key_present() == ai_rule.api_key_present())"
)
out = run_in_subprocess(code_default, {}).splitlines()
check("AI_PROVIDER 미설정 → 기본값은 여전히 'gemini'", out[0] == "gemini", out)
check("AI_PROVIDER 미설정 → _active_model_name() == _MODEL (공식 라벨과 동일)",
      out[1] == "True", out)
check("AI_PROVIDER 미설정 → _active_key_present() == api_key_present() (공식 판정과 동일)",
      out[2] == "True", out)

# ---------------------------------------------------------------------------
# 2. AI_PROVIDER=openai여도 "공식 준비 상태" 함수(api_key_present/live_status/
#    _MODEL)는 여전히 Gemini만 본다 — GPT 설정 때문에 '준비됨'이 거짓으로 뜨지 않음.
# ---------------------------------------------------------------------------
code_official_untouched = (
    "import ai_rule;"
    "print(ai_rule._MODEL);"
    "print(ai_rule.api_key_present());"
    "print(ai_rule.live_status()['model'])"
)
out2 = run_in_subprocess(code_official_untouched, {"AI_PROVIDER": "openai",
                                                     "OPENAI_API_KEY": "sk-test-dummy"}).splitlines()
check("AI_PROVIDER=openai + OPENAI_API_KEY 있어도 _MODEL은 여전히 Gemini 모델명",
      "gemini" in out2[0].lower(), out2)
check("AI_PROVIDER=openai + OPENAI_API_KEY 있어도 api_key_present()는 GEMINI_API_KEY 기준(False, 안 줬으므로)",
      out2[1] == "False", out2)
check("AI_PROVIDER=openai여도 live_status()['model']은 여전히 Gemini 모델명",
      "gemini" in out2[2].lower(), out2)

# ---------------------------------------------------------------------------
# 3. 캐시 네임스페이스 분리 — GPT 결과와 Gemini 결과가 같은 payload여도 절대
#    같은 파일명을 쓰지 않는다.
# ---------------------------------------------------------------------------
code_cache_ns = (
    "import ai_rule;"
    "print(ai_rule._cache_path('compile', 'same-payload').name)"
)
p_gemini = run_in_subprocess(code_cache_ns, {}).splitlines()[-1]
p_openai = run_in_subprocess(code_cache_ns, {"AI_PROVIDER": "openai"}).splitlines()[-1]
check("동일 payload라도 AI_PROVIDER=gemini/openai의 캐시 파일명이 서로 다름 (절대 안 섞임)",
      p_gemini != p_openai, {"gemini": p_gemini, "openai": p_openai})
check("AI_PROVIDER=openai 캐시 파일명에는 '_openai_' 네임스페이스가 들어감",
      "_openai_" in p_openai, p_openai)
check("AI_PROVIDER=gemini(기본) 캐시 파일명에는 '_openai_'가 안 들어감(기존 캐시 규칙 그대로)",
      "_openai_" not in p_gemini, p_gemini)

# ---------------------------------------------------------------------------
# 4. 라벨링 — AI_PROVIDER=openai면 model 필드가 절대 "gemini..."로 안 찍히고
#    'DEV25 공식 System B'라고 명확히 표시된다 (compile_rule 경유). 2026-08-31
#    이전엔 'GPT 실험용'이었으나 GPT가 공식 provider로 확정되며 문구가 바뀌었다
#    — "어느 provider가 실제로 호출됐는지 항상 구분된다"는 안전장치 자체는 동일.
# ---------------------------------------------------------------------------
code_label = (
    "import ai_rule;"
    "cand = ai_rule.compile_rule('60만원 이상이면 0.2%p 우대');"
    "print(cand.model)"
)
label_gemini = run_in_subprocess(code_label, {}).splitlines()[-1]
label_openai = run_in_subprocess(code_label, {"AI_PROVIDER": "openai"}).splitlines()[-1]
check("AI_PROVIDER 미설정 → RuleCandidate.model에 'DEV25 공식 System B' 문구가 없음",
      "DEV25 공식 System B" not in label_gemini, label_gemini)
check("AI_PROVIDER=openai → RuleCandidate.model에 'DEV25 공식 System B'가 명확히 찍힘(gemini 라벨과 혼동 불가)",
      "DEV25 공식 System B" in label_openai and not label_openai.lower().startswith("gemini"), label_openai)

# ---------------------------------------------------------------------------
# 5. wide_compiler(DEV25 System B가 실제로 쓰는 모듈)의 model_name도 동일하게
#    라벨링된다 — dev25_runner의 xlsx 결과 컬럼에 그대로 들어가는 값이다.
# ---------------------------------------------------------------------------
code_wide = (
    "import wide_compiler;"
    "fields, meta = wide_compiler.compile_raw('60만원 이상이면 0.2%p 우대', rule_id='T1');"
    "print(meta['model_name'])"
)
wide_gemini = run_in_subprocess(code_wide, {}, cwd=ABLATION_DIR).splitlines()[-1]
wide_openai = run_in_subprocess(code_wide, {"AI_PROVIDER": "openai"}, cwd=ABLATION_DIR).splitlines()[-1]
check("wide_compiler.compile_raw() model_name — AI_PROVIDER 미설정이면 'DEV25 공식 System B' 없음",
      "DEV25 공식 System B" not in wide_gemini, wide_gemini)
check("wide_compiler.compile_raw() model_name — AI_PROVIDER=openai면 'DEV25 공식 System B'가 찍힘 "
      "(DEV25_RESULTS.xlsx의 model_name 컬럼이 실제로 이 값을 씀)",
      "DEV25 공식 System B" in wide_openai, wide_openai)

# ---------------------------------------------------------------------------
# 6. dev25_runner — is_mock 판정과 안내 문구가 실제로 쓰인 provider 기준으로
#    정확한지 (Gemini 키가 없어도 OpenAI 키가 있으면 mock이 아니라고 정확히 판단).
# ---------------------------------------------------------------------------
_saved_env = {k: os.environ.get(k) for k in ("AI_PROVIDER", "OPENAI_API_KEY", "GEMINI_API_KEY")}
for k in list(_saved_env):
    os.environ.pop(k, None)
try:
    os.environ["AI_PROVIDER"] = "openai"
    os.environ["OPENAI_API_KEY"] = "sk-test-dummy-for-active-key-check"
    importlib.invalidate_caches()
    if "ai_rule" in sys.modules:
        importlib.reload(sys.modules["ai_rule"])
    else:
        import ai_rule  # noqa: F401
    import ai_rule as _ar
    check("AI_PROVIDER=openai + OPENAI_API_KEY만 있어도 _active_key_present()=True "
          "(GEMINI_API_KEY 없어도 '키 없음'으로 오판하지 않음)",
          _ar._active_key_present() is True)
    check("이 상황에서 api_key_present()(공식, Gemini 전용)는 여전히 False",
          _ar.api_key_present() is False)
finally:
    for k, v in _saved_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    if "ai_rule" in sys.modules:
        importlib.reload(sys.modules["ai_rule"])

# ---------------------------------------------------------------------------
# 7. dev25_runner — 2026-08-31 GPT가 공식 System B provider로 확정되며 파일명
#    배정이 뒤집혔다: AI_PROVIDER=openai가 이제 공식 파일명(DEV25_RESULTS.xlsx)을
#    쓰고, AI_PROVIDER 미설정(gemini)이 참고용 파일명(DEV25_RESULTS_GEMINI_
#    REFERENCE.xlsx)을 쓴다. __main__ 블록(서브프로세스 없이는 직접 호출 불가)의
#    파일명 결정 로직을 소스에서 직접 검증한다 — "공식 산출물을 절대 덮어쓰지
#    않는다"는 약속의 핵심은 그대로, 어느 쪽이 공식인지만 바뀌었다.
# ---------------------------------------------------------------------------
_runner_src_path = os.path.join(ABLATION_DIR, "dev25_runner.py")
with open(_runner_src_path, "r", encoding="utf-8") as f:
    _runner_src = f.read()
check("dev25_runner.py __main__ — AI_PROVIDER=openai 분기가 공식 파일명(DEV25_RESULTS.xlsx)을 씀",
      "DEV25_RESULTS.xlsx" in _runner_src)
check("dev25_runner.py __main__ — AI_PROVIDER 미설정(gemini) 분기는 참고용 파일명(DEV25_RESULTS_GEMINI_REFERENCE.xlsx)을 씀",
      "DEV25_RESULTS_GEMINI_REFERENCE.xlsx" in _runner_src)
check("dev25_runner.py __main__ — GPT 공식 System B 실행임을 콘솔에 명시함",
      "공식 System B(GPT)" in _runner_src)

# ---------------------------------------------------------------------------
# 8. 실측 버그 회귀 — 2026-08-30, 동학이 실제 OPENAI_API_KEY로 DEV25 25문항을
#    돌려서 System B 75건 전부 HTTP 400으로 실패하는 걸 발견했다. 원인 2가지를
#    고쳤고, 재발하지 않는지 여기서 고정한다.
# ---------------------------------------------------------------------------
code_nested_schema = (
    "import sys; sys.path.insert(0, '../ablation');"
    "import ai_rule, json;"
    "from wide_compiler import _WIDE_SCHEMA;"
    "conv = ai_rule._gemini_schema_to_openai_strict(_WIDE_SCHEMA);"
    "print(json.dumps(conv['properties']['tiers']['items']))"
)
tiers_item_json = run_in_subprocess(code_nested_schema, {}).splitlines()[-1]
import json as _json
tiers_item = _json.loads(tiers_item_json)
check("8a. _gemini_schema_to_openai_strict — 실제 DEV25 스키마(_WIDE_SCHEMA)의 중첩 object"
      "(tiers.items)에도 additionalProperties=false가 재귀적으로 적용됨 "
      "(최상위만 처리하던 옛 버전이 System B 75건 전원 400 에러로 실패하게 만든 원인)",
      tiers_item.get("additionalProperties") is False, tiers_item)
check("8a. tiers.items의 모든 필드(threshold/effect_value)가 required에 재귀적으로 들어감"
      "(OpenAI strict 모드는 중첩 object도 전체 required를 요구함)",
      set(tiers_item.get("required", [])) == {"threshold", "effect_value"}, tiers_item)

code_httperror_body = """
import sys, io, json
sys.path.insert(0, '.')
from unittest.mock import patch
import urllib.error
import ai_rule

fake_body = json.dumps({'error': {'message':
    "Invalid schema for response_format 'extraction': "
    "In context=(), 'additionalProperties' is required to be supplied and to be false."}}).encode()
err = urllib.error.HTTPError('https://api.openai.com/v1/chat/completions', 400,
                              'Bad Request', {}, io.BytesIO(fake_body))
with patch('urllib.request.urlopen', side_effect=err):
    result = ai_rule._call_openai('prompt', {'type': 'object', 'properties': {}})
print(result is None)
print('additionalProperties' in (ai_rule.last_error() or ''))
"""
out8b = run_in_subprocess(code_httperror_body, {"AI_PROVIDER": "openai",
                                                  "OPENAI_API_KEY": "sk-test-dummy"}).splitlines()
check("8b. _call_openai() — HTTPError가 나도 예외 없이 None을 반환함(계약 유지)",
      out8b[0] == "True", out8b)
check("8b. _call_openai() — OpenAI 응답 본문(구체적 오류 메시지)이 last_error()에 실제로 담김"
      "(옛 버전은 str(e)만 써서 'HTTP Error 400: Bad Request'라는 원인 불명 문구만 남았다 — "
      "동학이 실제로 겪은 디버깅 곤란함의 원인이었다)",
      out8b[1] == "True", out8b)

print(f"\n{passed} passed, {failed} failed")
if failed:
    raise SystemExit(1)
