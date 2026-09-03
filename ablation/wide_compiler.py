# -*- coding: utf-8 -*-
"""System B/C 컴파일러 — 약관 원문 → blind25_fixed.ExtendedRuleSchema(14필드).

박승렬이 준 세 파일(ai_rule.py / baseline_regex.py / blind25_fixed.py)에는
System A(정규식 기준선)와 Gate(EvidenceGate)만 있고, System B/C가 호출할
"Gemini로 14필드 넓은 스키마를 뽑는 컴파일러"는 없다. 이 파일이 그 빠진 조각이다.

**새 호출 경로를 만들지 않는다.** mvp/ai_rule.py가 이미 만든
  - google.genai SDK 호출 (_call_gemini)
  - 라이브 우선 → 실패 시 캐시 (_invoke)
  - 캐시 파일 / builtin 캐시 폴백
  - _LAST_ERROR 정직한 실패 사유 기록
을 그대로 재사용한다. ai_rule.py는 COMPILED_FIELDS 6개만 컴파일하도록 짜여 있어서
(대표사례에 필요한 최소셋이라는 팀의 명시적 설계 판단, ai_rule.py 상단 주석 참고)
DEV25 SCHEMA가 요구하는 14필드에는 못 쓴다 — 그래서 프롬프트/스키마만 넓게 새로 짜고
호출·캐시·에러 처리는 ai_rule의 내부 헬퍼(_invoke)를 그대로 부른다.

System B = compile_raw()   Gemini 호출, 넓은 스키마 추출, Gate 없음.
System C = gate_only()     **Gemini를 다시 호출하지 않는다.** System B가 이미 뽑은
                            fields를 그대로 받아 blind25_fixed.EvidenceGate만 적용한다
                            (박승렬 지시: "C는 Gemini 다시 호출하면 안 되고 B에서 나온
                            결과 그대로 재사용해서 Evidence/Schema Gate만 적용"). 실제
                            호출 조립은 dev25_runner.py가 한다 — B의 3회 결과를 각각
                            gate_only()에 넘겨 C의 3회를 만든다.
            compile_with_gate()  위 조합을 혼자 쓰고 싶을 때만 쓰는 편의 함수 —
                            이건 내부적으로 compile_raw()를 새로 호출하므로 DEV25
                            runner의 System C 자리에는 쓰지 않는다.

GEMINI_API_KEY가 없으면 (이 개발 환경처럼) "그럴듯한 가짜 응답을 지어내지" 않는다.
ai_rule.py와 같은 원칙 — 모르면 비워두고 정직하게 실패로 표시한다. 실제 DEV25 결과로
쓰려면 반드시 실제 키로 재실행해야 한다 (PROJECT_CURRENT_STATE.md §6, dev25_runner.py
자체 주석과 동일한 제약).
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.environ.get("AR_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "mvp"))
sys.path.insert(0, os.path.join(ROOT, "ablation"))

import ai_rule  # noqa: E402  (google.genai 호출·캐시·환각 게이트 재사용)
from blind25_fixed import ExtendedRuleSchema, EvidenceGate  # noqa: E402

PROMPT_VERSION = "wide_compiler_v2_teamfrozen_2026-08-25_integrated_2026-08-28"

# ── Gemini 구조화 출력 스키마 (ExtendedRuleSchema 14필드와 1:1 대응) ──────────
# 전부 문자열로 받는다. StrongRegexBaseline과 형식을 맞춰야 두 System을 같은
# EvidenceGate로 채점할 수 있다 (숫자는 문자열 안에 원문 표기 그대로 담긴다.
# 예: "100만원 이상", "0.20%" — ai_rule.ungrounded_numbers가 문자열 속 숫자를 뽑아
# 원문과 대조하므로, 값을 미리 정수로 바꾸면 접지 검사가 오히려 부정확해진다).
_WIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "rule_id": {"type": "string"},
        "target_event": {"type": "string"},
        "condition": {"type": "string"},
        "effect": {"type": "string"},
        "nested_or_conditions": {"type": "array", "items": {"type": "string"}},
        "tiers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "threshold": {"type": "string"},
                    "effect_value": {"type": "string"},
                },
            },
        },
        "window": {"type": "string"},
        "effect_value": {"type": "string"},
        "exception": {"type": "string"},
        "attribution_rule": {"type": "string"},
        "grace_period": {"type": "string"},
        "recalc_frequency": {"type": "string"},
        "cap_or_rate_floor": {"type": "string"},
        "reversible_or_retroactive_restore": {"type": "string"},
    },
}

# 2026-08-28: 박승렬 확인 회신으로 팀이 2026-08-25에 실제로 Freeze한 System B 프롬프트
# 원문을 받았다 — 아래 _TEAM_FROZEN_SYSTEM_PROMPT가 그 원문 그대로다(한 글자도 안 고침).
# 이 세션이 팀 파일을 못 받아서 임시로 새로 짰던 예전 프롬프트는 이제 이 원문으로
# 교체한다. 원문은 "행동 규칙 5개"만 정의하고 14개 필드 이름 자체는 나열하지 않는데
# (response_schema가 필드명/타입을 강제하므로 원래 설계상 필요 없음), 실제로 우리가
# 쓰는 파이프라인은 스키마와 별개로 "이 필드에 뭘 채워야 하는지" 설명도 프롬프트 안에
# 있어야 모델이 제대로 채운다 — 그래서 원문 뒤에 필드 설명(_FIELD_GUIDE)을 그대로 이어
# 붙인다. 필드 설명 문구는 원문이 아니라 이 세션이 추가한 보충 설명이라는 걸 명확히
# 구분해서 남겨둔다.
_TEAM_FROZEN_SYSTEM_PROMPT = """[SYSTEM PROMPT - FIXED]
You are a precise Financial Contract Logic Extractor. Extract all rules into the provided JSON schema.

Rules:
1. Extract ALL tier ranges into the `tiers` array. Do NOT pick only the first number.
2. Normalize compound logic into `nested_or_conditions` when multiple OR conditions exist.
3. Map exceptions (e.g., "단, ~ 제외") explicitly to `exception`.
4. Capture precise numeric values including units (%p, 원, 개월) into `effect_value`, `window`, and `cap_or_rate_floor`.
5. Strictly adhere to the output JSON format without hallucinating facts outside the source text."""

# 원문(위)이 언급하지 않는 나머지 필드(rule_id/target_event/condition/effect/
# attribution_rule/grace_period/recalc_frequency/reversible_or_retroactive_restore)에
# 대한 설명 — 팀 프롬프트 원문이 아니라 이 세션이 보충한 부분.
_FIELD_GUIDE = """
Field guide (스키마 14필드 중 위 5개 규칙이 직접 언급하지 않는 필드에 대한 보충 설명 —
이 부분은 팀 원문이 아니라 이 세션이 스키마와 맞추기 위해 추가함):
rule_id             이 규칙을 식별할 짧은 이름 (없으면 비움)
target_event        이 조항이 적용되는 행동/이벤트 (예: 카드 이용실적)
condition           적용 조건 서술 (예: "최근 3개월 60만원 이상 이용")
effect              조건 충족 시 효과 서술
attribution_rule    실적 인정을 위한 귀속조건. 원문 표현 그대로. 없으면 비움
grace_period        유예 기간이 명시되어 있으면 그대로. 없으면 비움
reversible_or_retroactive_restore  복구/소급 적용 관련 서술이 있으면 그대로. 없으면 비움

tiers를 채웠으면 effect_value(단일값)는 비워두세요 — 같은 정보를 두 번 넣지 않습니다.
숫자를 담는 필드는 원문에 쓰인 표기를 그대로 옮기세요(단위를 임의로 바꾸거나 반올림하지 않음).

[조항 원문]
{clause}
"""

_WIDE_PROMPT = _TEAM_FROZEN_SYSTEM_PROMPT + "\n" + _FIELD_GUIDE


def _prompt_hash() -> str:
    return hashlib.sha256((_WIDE_PROMPT + PROMPT_VERSION).encode("utf-8")).hexdigest()[:12]


def _clean(data: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], bool, List[str]]:
    """빈 문자열/빈 배열/None을 걷어내고 ExtendedRuleSchema로 필드 단위 검증한다.

    반환: (정제된 필드, schema_valid, 필드별 검증 실패 로그)
    schema_valid는 "Gemini가 응답을 주긴 줬는데 그 안에 스키마를 어긴 필드가
    하나라도 있었는가"를 뜻한다 — data 자체가 없으면(호출 실패) 검증할 대상이
    없으므로 True로 둔다(무응답과 "응답은 왔는데 형식이 틀림"을 구분하기 위함).
    """
    if not data:
        return {}, True, []

    def _stringify(v: Any) -> Any:
        # 스키마는 전부 문자열 필드인데, Gemini가 숫자처럼 보이는 값을 구조화 출력
        # 스펙과 다르게 실제 숫자 타입(0.2)으로 보낼 때가 있다. pydantic이 이걸
        # 곧바로 거부하면 그 필드 하나 때문에 전체가 날아가므로, 검증 전에
        # 문자열로 바꿔서 원래 의도(원문 표기 그대로)에 최대한 맞춘다.
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return str(v)
        return v

    trimmed: Dict[str, Any] = {}
    for k, v in data.items():
        if k not in ExtendedRuleSchema.model_fields:
            continue
        if k == "tiers" and isinstance(v, list):
            v = [{tk: _stringify(tv) for tk, tv in t.items()} if isinstance(t, dict) else t for t in v]
        elif k == "nested_or_conditions" and isinstance(v, list):
            pass
        else:
            v = _stringify(v)
        if v in (None, "", [], {}):
            continue
        trimmed[k] = v

    # 필드 하나가 스키마를 어겨도(예: tiers 안 원소 형태가 틀림) 그 필드만 버리고
    # 나머지는 살린다 — 통째로 폐기하지 않는다. (전체 한 번에 검증했다가 실패하면
    # 전부 버려지던 버그를 여기서 필드 단위로 나눠서 고쳤다.)
    result: Dict[str, Any] = {}
    errors: List[str] = []
    for k, v in trimmed.items():
        try:
            single = ExtendedRuleSchema(**{k: v})
        except Exception as e:
            errors.append(f"schema:{k}: {e}")
            continue
        dumped = single.model_dump(exclude_none=True, exclude_defaults=True)
        if k in dumped:
            result[k] = dumped[k]
    return result, (len(errors) == 0), errors


# 429(RESOURCE_EXHAUSTED)/5xx/timeout에만 재시도한다 — 키 없음/스키마 오류처럼
# 재시도해도 안 될 실패나, "답이 마음에 안 든다"는 이유로는 절대 재시도하지 않는다
# (박승렬 지시: 유효한 응답이 한 번 나오면 그걸 그대로 쓴다). 2026-08-26 실측:
# DEV25 175행(호출 150회)을 쉬지 않고 쏘면 무료 등급 분당 한도에 걸려 초반 몇 건만
# 성공하고 나머지가 전부 막혔다.
_RATE_LIMIT_RETRY_DELAYS = (15, 30, 60)  # 초, 점점 늘려가며 최대 3회 재시도

_HTTP_STATUS_RE = re.compile(r"\b([45]\d{2})\b")


def _extract_http_status(err: Optional[str]) -> Optional[int]:
    """에러 문자열에서 HTTP 상태코드를 뽑는다 (예: "HTTP Error 429: ...", "500 Internal ..."). 못 찾으면 None."""
    if not err:
        return None
    m = _HTTP_STATUS_RE.search(err)
    return int(m.group(1)) if m else None


def _is_retryable(err: Optional[str]) -> bool:
    """429/5xx/timeout/network(연결 자체가 안 된 경우)일 때만 True. 스키마 오류·
    키 없음·JSON 파싱 실패 등은 재시도해도 결과가 바뀌지 않으므로 False — 여기서
    걸러야 불필요한 대기 시간을 안 쓴다(2026-08-31: network 오류 탐지를 명시적으로
    추가 — 예전엔 "timeout"이라는 글자가 없는 연결 실패(DNS/연결거부 등)가
    재시도 대상에서 조용히 빠졌다)."""
    if not err:
        return False
    if "429" in err or "RESOURCE_EXHAUSTED" in err:
        return True
    status = _extract_http_status(err)
    if status is not None and status >= 500:
        return True
    low = err.lower()
    if "timeout" in low or "timed out" in low or "time out" in low:
        return True
    _NETWORK_MARKERS = (
        "urlerror", "connectionerror", "connectionreseterror", "brokenpipeerror",
        "gaierror", "network", "connection refused", "name or service not known",
        "temporary failure in name resolution", "unreachable",
    )
    if any(marker in low for marker in _NETWORK_MARKERS):
        return True
    return False


def compile_raw(source_text: str, rule_id: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """System B: Gemini 넓은 스키마 추출, Gate 없음.

    ai_rule._invoke를 그대로 재사용 — 라이브 우선, 실패하면 캐시, 어느 쪽인지
    source로 표시된다. 키/SDK/캐시가 전부 없으면 (None, "cache")가 돌아온다 —
    이 경우 정직하게 빈 결과 + 실패 사유를 meta에 남긴다(가짜 값으로 채우지 않는다).
    429/5xx/timeout/network면 잠깐 쉬었다가 최대 3번까지 다시 시도한다. 그 외 실패
    (스키마 오류, 키 없음, 파싱 실패 등)는 재시도하지 않고 그대로 실패 처리한다.
    "답이 마음에 안 들어서" 다시 부르는 재시도는 여기 어디에도 없다 — 유효한
    응답이 한 번 오면(=재시도 대상이 아니면) 그걸 그대로 최종값으로 쓴다.

    EVAL_STRICT=1(공식 평가모드, ai_rule.EVAL_STRICT)일 때는 위 "실패하면 캐시"가
    적용되지 않는다 — live 실패 시 ai_rule._invoke가 캐시를 읽지 않고 그대로 실패를
    반환하고(source="run_failure"), 이 함수는 그걸 reject_reason에 "RUN_FAILURE
    (EVAL_STRICT)"로 명시한다. HTTP 200을 받고도 스키마/내용 검증에서 걸러진
    경우도 EVAL_STRICT에서는 동일하게 RUN_FAILURE로 표시된다.
    """
    t0 = time.time()
    # .format()이 아니라 치환을 쓴다 — 프롬프트 안에 {threshold, effect_value} 같은
    # 예시 중괄호가 있어서 str.format()이 이걸 플레이스홀더로 오인해 KeyError가 난다.
    prompt = _WIDE_PROMPT.replace("{clause}", source_text.strip())

    retry_count = 0
    error_log: List[str] = []

    data, source = ai_rule._invoke("wide_compile", source_text, prompt, _WIDE_SCHEMA)
    if data is None and ai_rule.last_error():
        error_log.append(ai_rule.last_error())

    for delay in _RATE_LIMIT_RETRY_DELAYS:
        if data is not None or not _is_retryable(ai_rule.last_error()):
            break
        retry_count += 1
        time.sleep(delay)
        data, source = ai_rule._invoke("wide_compile", source_text, prompt, _WIDE_SCHEMA)
        if data is None and ai_rule.last_error():
            error_log.append(ai_rule.last_error())

    latency_ms = int((time.time() - t0) * 1000)

    fields, schema_valid, schema_errors = _clean(data)
    error_log.extend(schema_errors)

    ok = bool(fields)  # rule_id를 채우기 전에 판단 — rule_id는 우리가 넣은 fallback이지
                       # AI가 뽑은 내용이 아니므로 "추출 성공" 여부에 넣으면 안 된다.
    if rule_id and not fields.get("rule_id"):
        fields["rule_id"] = rule_id

    final_err = ai_rule.last_error() if not ok else None
    http_status = _extract_http_status(final_err)
    if http_status is None and source == ai_rule.SOURCE_LIVE:
        # source가 SOURCE_LIVE라는 것 자체가 "HTTP 응답은 정상적으로 받았다"는 뜻이다
        # (ai_rule._call_ai가 None이 아닌 걸 반환했으므로) — ok가 False라도(=이후
        # 스키마/내용 검증에서 걸러진 경우) http_status는 정직하게 200으로 남긴다.
        # "호출이 됐는가"와 "결과를 받아들일 수 있는가"는 별개 질문이라 섞지 않는다.
        http_status = 200

    if not ok:
        if ai_rule.EVAL_STRICT:
            # 2026-08-31: EVAL_STRICT(공식 평가모드)에서는 live 실패든(=source가
            # SOURCE_RUN_FAILURE) HTTP 200을 받고도 스키마/내용 검증에서 걸러졌든
            # (=source가 SOURCE_LIVE인데 ok=False) 둘 다 "RUN_FAILURE"로 명시
            # 표시한다 — 과거 cache로 조용히 대체되지 않았다는 걸 채점 파이프라인이
            # grep 하나로 구분할 수 있게 한다.
            reject_reason = f"RUN_FAILURE (EVAL_STRICT): {final_err or '스키마/내용 검증 실패 (추출된 필드 없음)'}"
        else:
            reject_reason = final_err or "추출된 필드 없음 (키/캐시 없음)"
    else:
        reject_reason = None

    meta = {
        # 2026-08-30: ai_rule._MODEL을 직접 쓰지 않는다 — AI_PROVIDER=openai일 때도
        # 항상 "gemini-..."라고 찍혀서 실제 호출된 provider를 알 수 없게 되는
        # 라벨링 버그가 되기 때문. ai_rule._active_model_name()이 실제로 어느
        # provider가 호출됐는지에 맞춰 라벨을 돌려준다(2026-08-31: GPT가 공식
        # System B provider로 확정되어 openai 분기 라벨은 "DEV25 공식 System B",
        # gemini 분기는 그대로 _MODEL — 둘을 절대 안 섞이게 구분하는 목적은 동일).
        "model_name": ai_rule._active_model_name() if source == ai_rule.SOURCE_LIVE
                      else f"{ai_rule._active_model_name()} (RUN_FAILURE/미실행)"
                      if source == ai_rule.SOURCE_RUN_FAILURE
                      else f"{ai_rule._active_model_name()} (캐시/미실행)",
        "prompt_version": f"{PROMPT_VERSION}_{_prompt_hash()}",
        "latency_ms": latency_ms,
        "raw_output_json": data,
        "source": source,
        "schema_valid": schema_valid,
        "accepted": "Y" if ok else "N",
        "reject_reason": reject_reason,
        "http_status": http_status,
        "retry_count": retry_count,
        "error_log": error_log,
    }
    return fields, meta


def gate_only(fields: Dict[str, Any], source_text: str) -> Tuple[str, Optional[str], int]:
    """System C 전용 진입점: 이미 뽑혀 있는 fields(=System B의 출력)에 Gate만
    적용한다. **여기서는 Gemini를 절대로 호출하지 않는다** — DEV25 runner가
    System B의 3회 결과를 그대로 넘겨서 이 함수만 부르면 C의 3회가 완성된다.

    반환: (accepted "Y"/"N", reject_reason, gate_latency_ms)
    """
    t0 = time.time()
    verdict = EvidenceGate.verify(fields, source_text)
    gate_latency_ms = int((time.time() - t0) * 1000)
    return ("Y" if verdict["accepted"] else "N"), verdict["reject_reason"], gate_latency_ms


def compile_with_gate(source_text: str, rule_id: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """단독 호출용 편의 함수(자가진단 등)다 — compile_raw()로 Gemini를 새로 한 번
    호출한 뒤 gate_only()를 적용한다. **DEV25 runner는 이 함수를 쓰지 않는다** —
    System C가 Gemini를 다시 호출하면 안 되기 때문에, runner는 System B의 이미
    계산된 결과를 gate_only()에 직접 넘긴다 (dev25_runner.py의 _row_from_c 참고)."""
    fields, meta = compile_raw(source_text, rule_id)
    meta = dict(meta)
    if meta["accepted"] == "N":
        return fields, meta
    accepted, reject_reason, gate_latency_ms = gate_only(fields, source_text)
    meta["accepted"] = accepted
    meta["reject_reason"] = reject_reason
    meta["gate_latency_ms"] = gate_latency_ms
    return fields, meta


__all__ = ["compile_raw", "gate_only", "compile_with_gate", "PROMPT_VERSION"]


if __name__ == "__main__":
    # 2026-08-30: 이 예시는 DEV25 공식 25문항(blind25_samples.json)이나 원장 37행 중
    # 어디에도 없는 완전히 지어낸 조항이다 — 반드시 그래야 한다. 예전 버전은 U005의
    # source_bundle_text를 글자 그대로(줄바꿈만 다르게) 여기 썼는데, ai_rule._cache_path
    # 는 공백을 전부 정규화한 뒤 해시하므로 그 차이가 사라져서 이 자가진단이 U005의
    # "실제 공식 캐시 슬롯"과 완전히 같은 파일(wide_compile[_openai]_94bb96dd34933d50
    # .json)을 썼다/읽었다 — 동학이 실제 GPT 키로 25문항을 돌린 뒤 이 자가진단을
    # 실행했다면 U005의 실측 결과를 조용히 덮어쓰거나, 반대로 자가진단이 매번 자기
    # 호출 없이 U005의 실측 캐시를 대신 읽어와 "성공"처럼 보이는 거짓 안정성을 줄
    # 수 있었다(실측 조사 결과 이번엔 아직 덮어써지지 않았음 — U005 캐시 내용은
    # 실제 DEV25 실행분 그대로였다). 자가진단용 예시는 앞으로도 공식 25문항/원장
    # 37행과 절대 겹치면 안 된다 — 겹치면 이 문제가 그대로 재발한다.
    src = ("예시 우대조건 - 모바일뱅킹 첫 로그인 시 우대금리 0.10%p 적용"
           "(신규 가입자 한정, 자동이체 등록 시 추가 0.05%p)")
    fields, meta = compile_raw(src, rule_id="SELFCHECK")
    print("compile_raw:", fields)
    print("meta:", {k: v for k, v in meta.items() if k != "raw_output_json"})
    fields2, meta2 = compile_with_gate(src, rule_id="SELFCHECK")
    print("compile_with_gate accepted:", meta2["accepted"], meta2["reject_reason"])
