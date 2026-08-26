"""ablation/baseline_regex.py (실제 팀 코드 v5) 단위 테스트.

parse()는 조항 문자열 하나에서 최대 6개 필드(threshold, effect_value, operator,
window, exception, attribution_rule)를 뽑는 dict를 반환하고, parse_tiers()는
계단형(다중 임계) 조항을 구간 리스트로 쪼갠다. 실제 값은 먼저 인터프리터로
확인한 뒤 그 결과를 그대로 회귀 테스트로 고정했다. (v5는 이전 세션에서 테스트하던
CandidateRule 기반 API가 아니라 dict/list를 직접 반환하므로 API가 바뀌었다.)"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ablation"))

import baseline_regex as br

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        print(f"✅ {name}")
        passed += 1
    else:
        print(f"❌ {name}")
        failed += 1


# --- 이상(>=) + 만원 단위 + 기간(개월) ---
r = br.parse("최근 3개월 60만원 이상 카드 이용실적이 있는 경우 우대금리 0.20%를 적용합니다.")
check("60만원 → threshold 600000", r.get("threshold") == 600000)
check("이상 → operator >=", r.get("operator") == ">=")
check("0.20% → effect_value 0.2", r.get("effect_value") == 0.2)
check("3개월 → window 3M", r.get("window") == "3M")

# --- 초과(>) + %p ---
r = br.parse("100만원 초과 시 0.3%p 적용")
check("100만원 → threshold 1000000", r.get("threshold") == 1_000_000)
check("초과 → operator >", r.get("operator") == ">")
check("0.3%p → effect_value 0.3", r.get("effect_value") == 0.3)

# --- 이하(<=) ---
r = br.parse("30만원 이하 입금 시 0.1% 적용")
check("이하 → operator <=", r.get("operator") == "<=")
check("30만원 → threshold 300000", r.get("threshold") == 300_000)

# --- 미만(<), 효과값 없는 조항 ---
r = br.parse("10만원 미만이면 적용되지 않습니다")
check("미만 → operator <", r.get("operator") == "<")
check("10만원 → threshold 100000", r.get("threshold") == 100_000)
check("효과값 없는 문장 → effect_value 미채움", "effect_value" not in r)

# --- 억 단위 ---
r = br.parse("1억원 이상 예치 시 우대금리 0.5%를 적용합니다.")
check("1억원 → threshold 100000000", r.get("threshold") == 100_000_000)

# --- 쉼표 구분 순수 숫자 + 원 ---
r = br.parse("1,000,000원 이상 입금 시 0.2% 적용")
check("1,000,000원 → threshold 1000000", r.get("threshold") == 1_000_000)

# --- 기간: 개월간 / 년 ---
r = br.parse("최근 12개월간 급여이체 실적이 있는 경우 0.3% 우대")
check("12개월간 → window 12M", r.get("window") == "12M")
check("금액 없는 조항 → threshold 미채움", "threshold" not in r)

r = br.parse("1년 이상 거래 시 0.1% 적용")
check("1년 → window 1Y", r.get("window") == "1Y")
check("1년 이상 → operator >=", r.get("operator") == ">=")

# --- 예외 절 추출 ---
r = br.parse("다만 신규 가입 고객은 제외합니다. 최근 3개월 60만원 이상 시 0.2% 적용.")
check("다만... → exception 필드 채움", r.get("exception") is not None)
check("exception 텍스트가 '다만'으로 시작", (r.get("exception") or "").startswith("다만"))
check("예외 절이 있어도 threshold는 정상 추출", r.get("threshold") == 600000)

# --- 귀속조건 추출 ---
r = br.parse("급여계좌를 당행으로 지정하는 경우 0.2% 우대금리를 적용합니다.")
check("계좌...지정 → attribution_rule 채움", r.get("attribution_rule") is not None)
check("attribution_rule에 '계좌'와 '지정' 포함",
      "계좌" in (r.get("attribution_rule") or "") and "지정" in (r.get("attribution_rule") or ""))

# --- 확신 없는 필드는 비운다 (연산자 표현이 전혀 없는 문장) ---
r = br.parse("우대금리는 상품설명서를 참고하시기 바랍니다.")
check("연산자 표현 없는 문장 → operator 미채움", "operator" not in r)
check("금액 없는 문장 → threshold 미채움", "threshold" not in r)

# --- 계단형(다중 임계) 처리: 금액 수 == 우대폭 수일 때만 tiers 채움 ---
tiers = br.parse_tiers("30만원 이상 0.1%, 60만원 이상 0.2%, 90만원 이상 0.3%")
check("계단형 3구간 모두 분리", tiers == [
    {"threshold": 300_000, "effect_value": 0.1},
    {"threshold": 600_000, "effect_value": 0.2},
    {"threshold": 900_000, "effect_value": 0.3},
])

check("단일 임계 조항은 tiers 비어있음 (parse()로 대표값만)",
      br.parse_tiers("60만원 이상이면 0.2% 적용") == [])

# 금액 수와 우대폭 수가 다르면(짝을 맞출 수 없으면) 안전하게 비운다
mismatched = br.parse_tiers("30만원 이상이면 우대, 60만원 이상이면 추가 우대, 90만원 이상이면 최대 0.3% 우대")
check("금액 수 ≠ 우대폭 수 → tiers 비어있음 (섣불리 추측하지 않음)", mismatched == [])

# --- VERSION 노출 확인 ---
check("VERSION == v5", br.VERSION == "v5")

# --- 실제 25건 BLIND25 원문으로 실측 (하드코딩 분기 없이 동일 parse() 전수 실행) ---
samples_path = os.path.join(os.path.dirname(__file__), "..", "ablation", "blind25_samples.json")
if os.path.exists(samples_path):
    samples = json.load(open(samples_path, encoding="utf-8"))
    success = sum(
        1 for s in samples
        if (lambda f: bool(f.get("threshold") or f.get("effect_value")))(br.parse(s["source_bundle_text"]))
    )
    print(f"\n실측: 25건 중 {success}건에서 threshold/effect_value 하나 이상 추출")
    check("실제 BLIND25 25건 기준 절반 이상에서 수치 추출 성공 (약한 baseline 아님)", success >= 12)
else:
    print("⚠️ blind25_samples.json 없음 — 실측 스킵")

print(f"\n{passed} passed, {failed} failed")
if failed:
    raise SystemExit(1)
