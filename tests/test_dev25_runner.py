"""dev25_runner.py 파이프라인 테스트 — 175행 정확히 나오는지, 스키마가 맞는지.

GEMINI_API_KEY 없이 실행 — 이 환경에는 키가 없으므로 B/C는 정직하게 추출 실패(accepted=N)로
채워진다. 이 테스트가 검증하는 건 "실제 Gemini 성능"이 아니라 "파이프라인이 175행을
스키마에 맞게 기계적으로 만들어내는지"다 (dev25_runner.py 자체 docstring과 동일한 전제)."""
import sys, os, json

ROOT = os.path.join(os.path.dirname(__file__), "..")
os.environ.setdefault("AR_ROOT", os.path.abspath(ROOT))
sys.path.insert(0, os.path.join(ROOT, "ablation"))
sys.path.insert(0, os.path.join(ROOT, "mvp"))

from dev25_runner import run

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        print(f"✅ {name}")
        passed += 1
    else:
        print(f"❌ {name}")
        failed += 1


rows, is_mock = run()
check("총 175행", len(rows) == 175)
check("GEMINI_API_KEY 없는 이 환경에서는 is_mock=True로 정직하게 표시됨", is_mock is True)

a = [r for r in rows if r["system"] == "A"]
b = [r for r in rows if r["system"] == "B"]
c = [r for r in rows if r["system"] == "C"]
check("A는 25행 (샘플당 1회)", len(a) == 25)
check("B는 75행 (샘플당 3회)", len(b) == 75)
check("C는 75행 (샘플당 3회)", len(c) == 75)

REQUIRED_COLS = {"sample_id", "system", "run_id", "model_name", "prompt_version",
                  "raw_output_json", "parsed_output_json", "accepted", "reject_reason", "latency_ms"}
check("OUTPUT_TEMPLATE 10개 컬럼 전부 존재", all(REQUIRED_COLS <= set(r.keys()) for r in rows))
check("모든 accepted는 Y/N 중 하나", all(r["accepted"] in ("Y", "N") for r in rows))

def _try_json(s):
    try:
        json.loads(s)
        return True
    except (TypeError, ValueError):
        return False


check("모든 raw_output_json이 파싱 가능한 JSON(null 포함)",
      all(_try_json(r["raw_output_json"]) for r in rows))

# System A는 이 환경에서도 LLM 없이 도는 결정론적 파서라 실제 추출이 일어난다 —
# 최소한 raw_output_json이 "{}"(완전 공백)만은 아니어야 한다는 걸 확인한다.
check("System A(정규식)는 이 환경에서도 실제로 무언가 추출함 (LLM 불필요)",
      any(json.loads(r["raw_output_json"]) for r in a))

# GEMINI_API_KEY가 없는 이 환경에서는 B/C가 정직하게 전부 거절되어야 한다 —
# 가짜 mock 값으로 accepted=Y를 만들어내면 안 된다(팀의 null-handling 원칙 위반).
check("키 없는 환경 → System B 전부 accepted=N (가짜 값 없음)",
      all(r["accepted"] == "N" for r in b))
check("키 없는 환경 → System C 전부 accepted=N (가짜 값 없음)",
      all(r["accepted"] == "N" for r in c))

sample_ids = {r["sample_id"] for r in rows}
check("25개 sample_id(U001~U025) 전부 포함", sample_ids == {f"U{n:03d}" for n in range(1, 26)})

print(f"\n{passed} passed, {failed} failed")
if failed:
    raise SystemExit(1)
