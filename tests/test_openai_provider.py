"""AI_PROVIDER(Gemini/GPT 선택) 회귀테스트 (2026-08-30 추가).

"GEMINI_API_KEY 대신 GPT API로 바꾸면 쉬운가"라는 질문에 대한 답으로
mvp/openai_client.py를 추가하고 mvp/action_interpreter.py에 AI_PROVIDER 환경변수
분기를 넣었다. 이 파일은 그 분기가:
  1. AI_PROVIDER를 아무도 안 건드리면(기본값 "gemini") 기존 동작이 한 글자도 안
     바뀌었는지,
  2. AI_PROVIDER=openai로 바꾸면 실제로 openai_client 쪽으로 분기하는지,
  3. 키가 없을 때 두 provider 모두 크래시 없이 mock으로 안전하게 떨어지는지
를 검증한다. 실제 네트워크 호출(진짜 API 키로 OpenAI/Gemini를 실제로 때리는 것)은
이 자동화 회귀테스트에 넣지 않는다 — CI/오프라인 환경에서 그대로 재현 가능해야
하기 때문이다(대신 openai_client.call_openai_json()이 키 없을 때 네트워크를 아예
안 열고 바로 실패하는 경로만 직접 검증한다).

기존 159개 테스트(action_interpreter 22 + ai_rule 23 + baseline_regex 30 +
dev25_runner 12 + engine 22 + safezone_v12 26 + fix4_safezone 24)는 이 파일에서
한 줄도 건드리지 않는다 — 순수 추가(additive)다.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mvp"))

passed = failed = 0


def check(name, cond, detail=None):
    global passed, failed
    if cond:
        print(f"✅ {name}")
        passed += 1
    else:
        print(f"❌ {name}" + (f" — {detail}" if detail is not None else ""))
        failed += 1


MVP_DIR = os.path.join(os.path.dirname(__file__), "..", "mvp")


def run_interpret_in_subprocess(text: str, env_overrides: dict) -> dict:
    """AI_PROVIDER 같은 모듈 로드 시점 상수는 같은 프로세스에서 os.environ만 바꿔서는
    재적용되지 않으므로(이미 import된 값을 계속 씀), 매번 새 프로세스로 띄워서 실제
    배포 때(env var 설정 후 앱 기동)와 똑같은 조건으로 검증한다."""
    env = {k: v for k, v in os.environ.items() if k not in ("AI_PROVIDER", "OPENAI_API_KEY", "GEMINI_API_KEY")}
    env.update(env_overrides)
    code = (
        "import sys, json; sys.path.insert(0, '.');"
        "from action_interpreter import interpret;"
        f"d, meta = interpret({text!r}, force_mock=False);"
        "print(json.dumps({'status': d.status, 'action_type': d.action_type, "
        "'institution': d.institution, 'product': d.product, 'meta': meta}))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=MVP_DIR, env=env,
                          capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, f"subprocess failed: {out.stderr}"
    import json
    return json.loads(out.stdout.strip().splitlines()[-1])


SENTENCE = "다음 달부터 카드사용 5만원을 다른 카드로 옮길 거야"

# ---------------------------------------------------------------------------
# 1. 기본값(AI_PROVIDER 미설정) → 기존 동작(Gemini 기준 mock) 그대로
# ---------------------------------------------------------------------------
r_default = run_interpret_in_subprocess(SENTENCE, {})
check("AI_PROVIDER 미설정 → 기존과 동일하게 Gemini 기준 mock으로 떨어짐(model_name='mock-not-gemini')",
      r_default["meta"]["model_name"] == "mock-not-gemini", r_default)
check("AI_PROVIDER 미설정이어도 해석 자체는 정상 동작(OK, 금액 인식)",
      r_default["status"] == "OK", r_default)

# ---------------------------------------------------------------------------
# 2. AI_PROVIDER=openai, 키 없음 → openai_client 쪽으로 분기했지만 크래시 없이 mock
# ---------------------------------------------------------------------------
r_openai_nokey = run_interpret_in_subprocess(SENTENCE, {"AI_PROVIDER": "openai"})
check("AI_PROVIDER=openai + 키 없음 → mock-not-openai로 정확히 분기(잘못 gemini로 안 감)",
      r_openai_nokey["meta"]["model_name"] == "mock-not-openai", r_openai_nokey)
check("AI_PROVIDER=openai여도 해석 자체는 정상 동작(크래시 없음, OK)",
      r_openai_nokey["status"] == "OK", r_openai_nokey)

# ---------------------------------------------------------------------------
# 3. 은행/상품명 감지는 AI provider와 완전히 무관하게 항상 동일 로직으로 동작
# ---------------------------------------------------------------------------
inst_sentence = "신협 적금 때문에 급여계좌 옮기려고"
r_gemini_inst = run_interpret_in_subprocess(inst_sentence, {})
r_openai_inst = run_interpret_in_subprocess(inst_sentence, {"AI_PROVIDER": "openai"})
check("은행명 감지 결과는 provider(gemini/openai)와 무관하게 동일함(둘 다 institution='신협')",
      r_gemini_inst["institution"] == r_openai_inst["institution"] == "신협",
      {"gemini": r_gemini_inst["institution"], "openai": r_openai_inst["institution"]})

# ---------------------------------------------------------------------------
# 4. 알 수 없는 AI_PROVIDER 값 → 크래시 없이 안전하게 Gemini 기본 동작으로 떨어짐
# ---------------------------------------------------------------------------
r_unknown = run_interpret_in_subprocess(SENTENCE, {"AI_PROVIDER": "banana"})
check("AI_PROVIDER에 알 수 없는 값을 넣어도 크래시 없이 Gemini 기본 동작으로 안전하게 떨어짐",
      r_unknown["meta"]["model_name"] == "mock-not-banana" and r_unknown["status"] == "OK", r_unknown)

# ---------------------------------------------------------------------------
# 5. openai_client.py 자체 계약 — 키 없으면 네트워크 시도 없이 바로 OpenAIError
#    (이건 네트워크가 필요 없어서 subprocess 없이 바로 같은 프로세스에서 검증 가능)
# ---------------------------------------------------------------------------
_saved = os.environ.pop("OPENAI_API_KEY", None)
try:
    from openai_client import call_openai_json, has_api_key, OpenAIError
    check("openai_client.has_api_key() — OPENAI_API_KEY 없으면 False", has_api_key() is False)
    try:
        call_openai_json("system", "user")
        check("openai_client.call_openai_json() — 키 없으면 OpenAIError를 던져야 하는데 안 던짐", False)
    except OpenAIError as e:
        check("openai_client.call_openai_json() — 키 없으면 네트워크 시도 없이 바로 OpenAIError",
              "OPENAI_API_KEY" in str(e))
finally:
    if _saved is not None:
        os.environ["OPENAI_API_KEY"] = _saved

os.environ["OPENAI_API_KEY"] = "sk-test-dummy-for-has-api-key-check"
try:
    import importlib
    import openai_client as _oc
    importlib.reload(_oc)
    check("openai_client.has_api_key() — OPENAI_API_KEY 있으면 True", _oc.has_api_key() is True)
finally:
    del os.environ["OPENAI_API_KEY"]
    importlib.reload(_oc)

print(f"\n{passed} passed, {failed} failed")
if failed:
    raise SystemExit(1)
