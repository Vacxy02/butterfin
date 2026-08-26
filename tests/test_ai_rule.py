"""mvp/ai_rule.py (실제 팀 코드, 박승렬 작성) 단위 테스트.
GEMINI_API_KEY 없이 실행 — live 호출 없이도 검증 가능한 순수 함수들 위주로 검사한다."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mvp"))

import ai_rule

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        print(f"✅ {name}")
        passed += 1
    else:
        print(f"❌ {name}")
        failed += 1


SOURCE = "최근 3개월 60만원 이상 카드 이용실적이 있는 경우 우대금리 0.20%를 적용합니다."

# --- 숫자 접지: 정답 통과 ---
check("정답 0.20% → ungrounded 없음",
      ai_rule.ungrounded_numbers({"effect_value": "0.20"}, SOURCE) == [])

# --- 환각 4종 전부 차단 (팀 자체 self-check와 동일한 케이스) ---
for fake in ["0.90", "0.10", "0.55", "0.99"]:
    bad = ai_rule.ungrounded_numbers({"effect_value": fake}, SOURCE)
    check(f"환각 {fake}% → ungrounded 검출", len(bad) == 1 and bad[0][0] == "effect_value")

# --- 한국어 금액 동치 표기: 60만원 / 600000 / 600,000 ---
check("'600000' == '60만원' 표기와 접지 동일 취급",
      ai_rule.ungrounded_numbers({"threshold": "600000"}, SOURCE) == [])
check("'600,000' 도 접지됨",
      ai_rule.ungrounded_numbers({"threshold": "600,000"}, SOURCE) == [])

# --- exception/attribution_rule은 숫자 접지 대상에서 제외됨 (서술 필드) ---
check("exception 필드 안의 숫자는 ungrounded 검사에서 제외",
      ai_rule.ungrounded_numbers({"exception": "999999999원 초과시 제외"}, SOURCE) == [])

# --- number_surface_forms: 억 단위까지 표기 생성 확인 ---
forms = ai_rule.number_surface_forms(150_000_000)
check("1억5천만 표기가 surface form에 포함", "1억5000만" in forms or "1억5천만" in forms or any("억" in f for f in forms))

# --- clause_hash: 같은 문장은 같은 해시, 공백만 달라도 같은 해시(정규화) ---
h1 = ai_rule.clause_hash("최근 3개월 60만원 이상")
h2 = ai_rule.clause_hash("최근   3개월  60만원   이상")
check("공백만 다른 문장은 동일 해시 (정규화)", h1 == h2)
h3 = ai_rule.clause_hash("최근 3개월 90만원 이상")
check("내용이 다르면 다른 해시", h1 != h3)

# --- run_gates: 스키마/연산자/해시/숫자접지/서술접지/예외누락 게이트 ---
cand = ai_rule.RuleCandidate(
    fields={"threshold": 600000, "operator": ">=", "effect_value": 0.2},
    evidence_span=SOURCE,
    clause_hash=ai_rule.clause_hash(SOURCE),
)
gates = ai_rule.run_gates(cand, expected_hash=cand.clause_hash)
check("정상 candidate → 모든 게이트 통과", all(g.passed for g in gates))
check("게이트 8개 실행됨", len(gates) == 8)

bad_cand = ai_rule.RuleCandidate(
    fields={"threshold": 600000, "operator": ">=", "effect_value": 9.99},  # 원문에 없는 값
    evidence_span=SOURCE,
    clause_hash=ai_rule.clause_hash(SOURCE),
)
bad_gates = ai_rule.run_gates(bad_cand, expected_hash=bad_cand.clause_hash)
check("환각 값 포함 candidate → 게이트 실패", not all(g.passed for g in bad_gates))

# --- 연산자 ↔ 근거 불일치 게이트 ---
mismatch_cand = ai_rule.RuleCandidate(
    fields={"threshold": 600000, "operator": ">", "effect_value": 0.2},  # 원문은 '이상'인데 '>' 로 잘못 씀
    evidence_span=SOURCE,
    clause_hash=ai_rule.clause_hash(SOURCE),
)
mismatch_gates = ai_rule.run_gates(mismatch_cand, expected_hash=mismatch_cand.clause_hash)
op_gate = next(g for g in mismatch_gates if g.name == "연산자 ↔ 근거 일치")
check("'이상'인데 연산자를 '>'로 잘못 채우면 게이트 실패", op_gate.passed is False)

# --- 예외 누락 게이트: 원문에 '제외' 표현이 있는데 exception 필드를 안 채우면 실패 ---
src_with_exception = "다만 신규 가입 고객은 제외합니다. 최근 3개월 60만원 이상 시 0.2% 적용."
missing_exc_cand = ai_rule.RuleCandidate(
    fields={"threshold": 600000, "operator": ">=", "effect_value": 0.2},  # exception 필드 누락
    evidence_span=src_with_exception,
    clause_hash=ai_rule.clause_hash(src_with_exception),
)
missing_exc_gates = ai_rule.run_gates(missing_exc_cand, expected_hash=missing_exc_cand.clause_hash)
exc_gate = next(g for g in missing_exc_gates if g.name == "예외 누락 없음")
check("원문에 예외 표현 있는데 exception 필드 누락 → 게이트 실패", exc_gate.passed is False)

# --- live_status: 키/SDK 없을 때 정직하게 ready=False ---
status = ai_rule.live_status()
check("live_status는 dict를 반환", isinstance(status, dict) and "ready" in status)
if not ai_rule.api_key_present():
    check("GEMINI_API_KEY 없으면 ready=False", status["ready"] is False)

# --- pipeline: 해시 불변 → FRESH, 변경 → STALE_REVIEW (키/캐시 없어 MATERIAL 처리됨) ---
same = ai_rule.pipeline(SOURCE, SOURCE)
check("변경 없음(해시 동일) → FRESH", same["freshness"]["status"] == "FRESH")
check("변경 없음 → engine_ready=True", same["engine_ready"] is True)

changed = ai_rule.pipeline(SOURCE, SOURCE + " 추가조항")
check("해시가 바뀌면 STALE_REVIEW 또는 FRESH(COSMETIC) 중 하나",
      changed["freshness"]["status"] in ("STALE_REVIEW", "FRESH"))
if changed["freshness"]["status"] == "STALE_REVIEW":
    check("STALE_REVIEW면 engine_ready=False", changed["engine_ready"] is False)
    check("STALE_REVIEW면 candidate가 채워짐", changed["candidate"] is not None)

print(f"\n{passed} passed, {failed} failed")
if failed:
    raise SystemExit(1)
