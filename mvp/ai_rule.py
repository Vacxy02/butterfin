# -*- coding: utf-8 -*-
"""Rule Intelligence Layer — 비정형 약관을 검증 가능한 계산규칙으로 바꾼다.

이 모듈은 **금융 판단을 하지 않는다.**

  - 돈을 계산하지 않는다
  - 조건 이탈 / 조건 유지를 결정하지 않는다
  - 사용자에게 무엇을 하라고 말하지 않는다

하는 일은 하나다. 은행이 약관을 바꿨을 때
**그 변경이 계산에 영향을 주는지 판정하고, 새 조항을 타입 있는 규칙 후보로 바꾼다.**
그 후보는 사람이 승인해야만 엔진에 들어간다.

    공식약관 → 변경탐지(해시) → [AI] 의미 유의성 → [AI] 규칙 컴파일
             → 기계 검증 → 사람 승인 → 검증된 규칙 → 결정론적 엔진

AI가 없으면 이 파이프라인이 멈춘다. 틀린 계산을 하는 게 아니라 **멈춘다.**
바뀐 조항은 STALE로 떨어지고, 사람이 다시 읽고 규칙을 쓸 때까지 판정이 재개되지 않는다.

환각 방어의 핵심은 6번 게이트다 —
**AI가 낸 숫자가 근거 문장에 글자로 존재하지 않으면 후보를 자동 폐기한다.**
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 상태값 ──────────────────────────────────────────────────────────────────
MATERIAL = "MATERIAL"
COSMETIC = "COSMETIC"

CANDIDATE = "CANDIDATE"
VERIFIED = "VERIFIED"
REJECTED = "REJECTED"

SOURCE_LIVE = "live"
SOURCE_CACHE = "cache"
SOURCE_RUN_FAILURE = "run_failure"  # EVAL_STRICT=1일 때 live 실패를 cache로 덮지 않고 남기는 표시

# Rule Compiler가 뽑는 필드 — 6개만 한다.
# 18개 전부는 20일에 불가능하고, 대표사례가 요구하는 건 이 6개다.
#   threshold / operator / window : 계산에 직접 들어감
#   effect_value                  : 우대폭
#   exception                     : 청약 당첨 예외 (숫자가 하나도 없는 조항)
#   attribution_rule              : 결제계좌 귀속조건 (금감원 민원 그 자체)
COMPILED_FIELDS = (
    "threshold",
    "operator",
    "window",
    "effect_value",
    "exception",
    "attribution_rule",
)

_ALLOWED_OPERATORS = {">=", ">", "<=", "<", "==", "!="}

_CACHE_DIR = Path(__file__).with_name("ai_cache")

_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
_API_KEY_ENV = "GEMINI_API_KEY"

# 마지막 라이브 호출 실패 사유. 조용히 캐시로 내려가면 원인을 알 수 없어서 남긴다.
# 2026-08-18에 gemini-2.5-flash가 신규 사용자에게 막혀 404가 났는데,
# except가 삼키는 바람에 "캐시 응답"으로만 보이고 원인이 안 보였다.
_LAST_ERROR: Optional[str] = None

# ── AI_PROVIDER(Gemini/GPT 선택) — 2026-08-30 실험용 추가, 2026-08-31 공식화 ──
# 이 파일(ai_rule.py)은 DEV25 System B/C의 공식 추출 경로다. 처음엔(2026-08-30)
# "GPT로 돌리면 어떻게 나오는지 실험만 해보고 싶다"는 요청으로 추가되어 "실험용/
# 비공식"으로 표시됐지만, 2026-08-31에 박승렬 지시로 **이번 대회의 공식 System B
# provider가 GPT로 확정**됐다 — 지금까지 진행한 DEV25 25문항×3회 GPT 실행이 공식
# 블라인드 재채점 대상이다(DEV25 자체는 development benchmark로 계속 유지, GPT
# 결과를 FINAL_UNSEEN 성능처럼 표현하지 않음). 이 확정은 provider 명칭/문서
# 정합성을 맞추는 것이며, 기존 GPT 결과 숫자를 보고 prompt/model을 바꾼 게
# 아니다(성능 맞춤 튜닝 아님) — 아래 구조(캐시 분리, 공식 상태 함수 분리)는
# 그대로 유지한다.
#
# AI_PROVIDER=openai로 돌린 결과는:
#   1) _MODEL/live_status()/api_key_present() 같은 "공식 상태" 함수는 여전히
#      GEMINI_API_KEY만 본다 — 이 함수들은 DEV25가 아니라 이 파일 전체(라이브
#      웹앱의 의미유의성 판정/규칙 컴파일 파이프라인 포함)의 "Gemini 키/SDK
#      준비 상태"를 보는 범용 함수라서 건드리지 않는다. DEV25 System B provider
#      확정과는 별개다 — 안 섞는다.
#   2) 캐시 파일명 자체를 분리한다(_cache_path 참고) — GPT로 뽑은 값이 Gemini
#      캐시와 파일명이 겹쳐서 섞이는 일이 구조적으로 불가능하다.
#   3) 기본값은 여전히 "gemini"다 — DEV25 공식 실행은 지금처럼 명시적으로
#      `AI_PROVIDER=openai`를 지정해서 돈다(자동으로 안 바뀜). 이 파일이 쓰이는
#      다른 곳(action_interpreter.py 등)은 AI_PROVIDER를 아예 참조하지 않으므로
#      이번 확정으로 영향받지 않는다.
AI_PROVIDER = os.environ.get("AI_PROVIDER", "gemini").strip().lower()
_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
_OPENAI_API_KEY_ENV = "OPENAI_API_KEY"

# ── EVAL_STRICT(공식 평가모드) — 2026-08-31, Freeze Candidate 정리 ──────────
# 기본값(EVAL_STRICT 미설정/"0")에서는 지금까지와 동일하게 live 실패 시 과거
# cache로 조용히 대체한다(데모/개발 모드 — 키가 없어도 화면이 죽지 않아야 함).
#
# EVAL_STRICT=1(공식 채점/제출 실행)일 때는 다르다 — "이번 실행이 실제로 API를
# 불러서 얻은 값"만 결과로 인정해야 평가가 의미 있으므로:
#   - live 호출이 어떤 이유로든 실패하면(키 없음/네트워크/파싱/스키마 불문)
#     과거 cache를 읽어 대체하지 않는다 — _invoke()가 SOURCE_RUN_FAILURE로 표시.
#   - 재시도는 여전히 429/5xx/timeout/network일 때만 한다(wide_compiler._is_retryable,
#     이 파일은 재시도 루프 자체를 갖지 않는다 — 재시도는 호출부 책임).
#   - 재시도가 끝난 뒤에도 실패면 그 행은 "RUN_FAILURE"로 명시적으로 남는다
#     (wide_compiler.compile_raw()의 reject_reason에 "RUN_FAILURE (EVAL_STRICT)"
#     접두사로 표시됨 — accepted=N과는 별개로 grep 가능하게).
# 아무도 EVAL_STRICT를 안 건드리면 기본값 "0"이라 기존 동작은 한 글자도 안 바뀐다.
EVAL_STRICT = os.environ.get("EVAL_STRICT", "0").strip() == "1"


def _active_model_name() -> str:
    """결과에 실제로 찍히는 model 라벨 — 오직 라벨링용이다.

    _MODEL 자체는 위 설명대로 절대 안 건드린다(그건 여전히 "공식 Gemini 준비
    상태"만 본다 — 라이브 웹앱의 범용 판정 함수이지 DEV25 System B provider
    확정과는 별개). 이 함수는 Materiality/RuleCandidate.model, 그리고
    wide_compiler의 DEV25 model_name 컬럼처럼 "이번 호출에 실제로 어떤
    모델이 쓰였는지" 사람이 읽는 값에만 쓰인다. 2026-08-31: GPT가 DEV25 공식
    System B provider로 확정되어 라벨에서 "실험용/비공식" 문구를 뗐다 — 아래
    구분(gemini 실행이면 그냥 _MODEL, openai 실행이면 별도 라벨)은 "어느 쪽이
    실제로 호출됐는지"를 여전히 명확히 갈라주기 위해 유지한다."""
    if AI_PROVIDER == "openai":
        return f"{_OPENAI_MODEL} (DEV25 공식 System B — GPT, 2026-08-31 확정)"
    return _MODEL


def _active_key_present() -> bool:
    """AI_PROVIDER가 실제로 쓰는 쪽의 키가 있는지 — api_key_present()(Gemini 전용,
    공식 준비 상태)와는 별개다. dev25_runner처럼 "지금 이 실행이 진짜 라이브
    호출인지 mock인지" 안내 문구를 정확히 찍어야 하는 곳에서만 쓴다."""
    if AI_PROVIDER == "openai":
        return bool(os.environ.get(_OPENAI_API_KEY_ENV, "").strip())
    return api_key_present()


# ── 결과 자료구조 ───────────────────────────────────────────────────────────
@dataclass
class Gate:
    """기계 검증 게이트 하나의 결과."""
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Materiality:
    """1단계 — 이 변경이 계산에 영향을 주는가."""
    verdict: str                      # MATERIAL / COSMETIC
    affected_field: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    reason: str
    source: str                       # live / cache
    model: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuleCandidate:
    """2단계 — 타입 있는 규칙 후보. 아직 엔진에 못 들어간다."""
    fields: Dict[str, Any]
    evidence_span: str
    clause_hash: str
    status: str = CANDIDATE
    gates: List[Gate] = field(default_factory=list)
    source: str = SOURCE_CACHE
    model: str = ""

    @property
    def all_passed(self) -> bool:
        return bool(self.gates) and all(g.passed for g in self.gates)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fields": self.fields,
            "evidence_span": self.evidence_span,
            "clause_hash": self.clause_hash,
            "status": self.status,
            "gates": [g.to_dict() for g in self.gates],
            "all_passed": self.all_passed,
            "source": self.source,
            "model": self.model,
        }


# ── 숫자 접지 (환각 방어의 핵심) ────────────────────────────────────────────
_MAN = 10_000
_EOK = 100_000_000


def _normalize(text: str) -> str:
    """비교 전 정규화. 전각/반각, 공백, 유니코드 형태를 맞춘다."""
    t = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", "", t)


def number_surface_forms(value: float) -> List[str]:
    """한국어 약관이 이 숫자를 적을 법한 표기들을 만든다.

    600000 이면 아래가 전부 같은 값이다.
        600000 / 600,000 / 60만 / 60만원
    0.2 이면
        0.2 / 0.20 / 연0.2
    이 목록 중 하나라도 근거 문장에 있으면 '접지됐다'고 본다.
    """
    forms: List[str] = []
    if value != value:                                   # NaN
        return forms

    is_int = abs(value - round(value)) < 1e-9
    if is_int:
        n = int(round(value))
        forms += [str(n), f"{n:,}"]
        if n >= _EOK and n % _EOK == 0:
            forms += [f"{n // _EOK}억", f"{n // _EOK}억원"]
        if n >= _MAN and n % _MAN == 0:
            m = n // _MAN
            forms += [f"{m}만", f"{m}만원", f"{m:,}만", f"{m:,}만원"]
        if n >= _EOK:
            eok, rest = divmod(n, _EOK)
            if rest and rest % _MAN == 0:
                forms.append(f"{eok}억{rest // _MAN}만")
    else:
        forms += [f"{value:g}", f"{value:.1f}", f"{value:.2f}"]
        # 0.20 → 0.2 처럼 뒤 0이 붙는 표기도 허용
        trimmed = f"{value:.2f}".rstrip("0").rstrip(".")
        if trimmed:
            forms.append(trimmed)

    return sorted({f for f in forms if f})


def _numbers_in(value: Any) -> List[float]:
    """필드 값에서 숫자를 뽑는다. 문자열 안의 숫자도 포함."""
    out: List[float] = []
    if isinstance(value, bool) or value is None:
        return out
    if isinstance(value, (int, float)):
        out.append(float(value))
    elif isinstance(value, str):
        for m in re.findall(r"\d[\d,]*\.?\d*", value):
            try:
                out.append(float(m.replace(",", "")))
            except ValueError:
                pass
    elif isinstance(value, (list, tuple)):
        for v in value:
            out += _numbers_in(v)
    elif isinstance(value, dict):
        for v in value.values():
            out += _numbers_in(v)
    return out


def ungrounded_numbers(fields: Dict[str, Any], evidence: str) -> List[Tuple[str, float]]:
    """근거 문장에 글자로 존재하지 않는 숫자를 전부 찾아낸다.

    **이게 이 모듈에서 제일 중요한 함수다.**
    AI가 그럴듯하게 지어낸 임계값은 여기서 전부 걸린다.
    """
    hay = _normalize(evidence)
    bad: List[Tuple[str, float]] = []
    for key, val in fields.items():
        if key in ("exception", "attribution_rule"):
            # 서술 필드는 숫자 접지 대상이 아니다. 문장 접지로 따로 검사한다.
            continue
        for num in _numbers_in(val):
            if not any(_normalize(f) in hay for f in number_surface_forms(num)):
                bad.append((key, num))
    return bad


def _span_grounded(text: Any, evidence: str, min_run: int = 6) -> bool:
    """서술 필드가 근거 문장에서 온 것인지 본다.

    AI가 요약하면서 표현을 바꾸는 건 허용하되,
    근거에 전혀 없는 내용을 만들어내는 건 막는다.
    연속 min_run 글자가 근거에 나타나면 접지된 것으로 본다.
    """
    if not text or not isinstance(text, str):
        return True                                       # 값이 없으면 검사 대상 아님
    hay, needle = _normalize(evidence), _normalize(text)
    if not needle:
        return True
    if needle in hay:
        return True
    return any(needle[i:i + min_run] in hay
               for i in range(0, max(1, len(needle) - min_run + 1)))


def clause_hash(clause_text: str) -> str:
    """원장과 같은 방식으로 조항 해시를 만든다."""
    return hashlib.sha256(_normalize(clause_text).encode("utf-8")).hexdigest()[:60]


# ── Gemini 호출 ─────────────────────────────────────────────────────────────
def _cache_path(kind: str, payload: str) -> Path:
    key = hashlib.sha256(_normalize(payload).encode("utf-8")).hexdigest()[:16]
    # AI_PROVIDER=openai일 때는 파일명에 "_openai_"를 끼워서 캐시 네임스페이스
    # 자체를 분리한다 — GPT로 뽑은 값이 Gemini 캐시 파일과 이름이 겹칠 수 없으니
    # "GPT(공식 System B) 결과가 Gemini(참고용) 캐시와 뒤섞이는" 상황이 구조적으로
    # 불가능하다(기본값 "gemini"일 때는 기존 파일명 그대로라 하위호환 유지).
    ns = f"{kind}_openai" if AI_PROVIDER == "openai" else kind
    return _CACHE_DIR / f"{ns}_{key}.json"


def _builtin(kind: str, payload: str) -> Optional[Dict[str, Any]]:
    """코드와 함께 배포되는 준비된 응답.

    파일 캐시보다 먼저 본다. 배포 대상이 읽기 전용 파일시스템이어도 동작해야 한다.
    """
    try:
        import ai_demo_data as demo                       # type: ignore
    except ImportError:
        return None
    table = {"materiality": demo.MATERIALITY, "compile": demo.COMPILE}.get(kind)
    if not table:
        return None
    want = _normalize(payload)
    for key, val in table.items():
        if _normalize(key) == want:
            return val
    return None


def _read_cache(kind: str, payload: str) -> Optional[Dict[str, Any]]:
    hit = _builtin(kind, payload)
    if hit is not None:
        return hit
    p = _cache_path(kind, payload)
    if p.is_file():
        try:
            return json.loads(io.open(p, encoding="utf-8").read())
        except (ValueError, OSError):
            return None
    return None


def _write_cache(kind: str, payload: str, data: Dict[str, Any]) -> bool:
    """라이브 응답을 파일로 남긴다. 실패해도 서비스는 계속된다.

    읽기 전용 배포에서는 실패가 정상이므로 예외를 올리지 않지만,
    **조용히 삼키지는 않는다** — 성공 여부를 돌려준다.
    """
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        io.open(_cache_path(kind, payload), "w", encoding="utf-8").write(
            json.dumps(data, ensure_ascii=False, indent=2))
        return True
    except OSError:
        return False


def api_key_present() -> bool:
    return bool(os.environ.get(_API_KEY_ENV, "").strip())


def sdk_present() -> bool:
    try:
        from google import genai  # noqa: F401  # type: ignore
        return True
    except ImportError:
        return False


def live_status() -> Dict[str, Any]:
    """실제로 라이브 호출이 가능한 상태인지 정확히 알려준다.

    키만 있고 SDK가 없으면 라이브가 아니다. 화면에 'live'라고 띄우면 거짓말이 된다.
    """
    key, sdk = api_key_present(), sdk_present()
    ready = key and sdk
    if ready and _LAST_ERROR:
        # 키도 SDK도 있는데 실제 호출이 깨진 상태. 준비됐다고 표시하면 거짓말이다.
        return {"ready": False, "api_key": key, "sdk": sdk, "model": _MODEL,
                "reason": f"호출 실패 — {_LAST_ERROR}"}
    if ready:
        reason = f"{_MODEL} 실시간 호출"
    elif not key and not sdk:
        reason = f"{_API_KEY_ENV} 미설정 · google-genai 미설치 → 준비된 응답 사용"
    elif not key:
        reason = f"{_API_KEY_ENV} 미설정 → 준비된 응답 사용"
    else:
        reason = "google-genai 미설치 (pip install google-genai) → 준비된 응답 사용"
    return {"ready": ready, "api_key": key, "sdk": sdk, "model": _MODEL, "reason": reason}


def last_error() -> Optional[str]:
    """마지막 라이브 호출이 왜 실패했는지. 성공했거나 시도 전이면 None."""
    return _LAST_ERROR


def _call_gemini(prompt: str, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """구조화 출력을 강제해서 한 번 호출한다. 실패하면 None.

    실패해도 예외를 올리지 않는다 — 서비스는 계속 돌아야 하고,
    응답을 못 얻으면 안전한 쪽(MATERIAL / 추출 실패)으로 떨어지기 때문이다.

    **다만 조용히 삼키지는 않는다.** 사유를 `_LAST_ERROR`에 남긴다.
    """
    global _LAST_ERROR
    key = os.environ.get(_API_KEY_ENV, "").strip()
    if not key:
        _LAST_ERROR = f"{_API_KEY_ENV} 미설정"
        return None
    try:
        from google import genai                          # type: ignore
        from google.genai import types                    # type: ignore
    except ImportError:
        _LAST_ERROR = "google-genai 미설치 (pip install google-genai)"
        return None
    try:
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.0,                          # 재현성. 금융이라 창의성은 해롭다
            ),
        )
        data = json.loads(resp.text)
        _LAST_ERROR = None
        return data
    except Exception as e:                                # 네트워크·쿼터·모델폐지·스키마 위반
        _LAST_ERROR = f"{type(e).__name__}: {str(e)[:200]}"
        return None


def _gemini_schema_to_openai_strict(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Gemini의 response_schema(일부 필드만 required)를 OpenAI strict json_schema
    형식(모든 필드가 required, additionalProperties=false)으로 옮긴다.

    OpenAI strict 모드는 "필수 아닌 필드"라는 개념이 없다 — 대신 required에 전부
    넣고, 원래 필수가 아니었던 필드는 null도 허용하는 타입으로 바꿔서 "채워도 되고
    안 채워도 된다"는 의미를 유지한다. 이건 순수한 스키마 표현 변환일 뿐, 실제로
    어떤 필드가 채워지는지는 여전히 모델(GPT) 응답에 달려있다.

    **재귀적으로 변환한다.** 처음 버전은 최상위 properties만 변환했는데, DEV25 System
    B의 실제 스키마(_WIDE_SCHEMA)에는 `tiers: {type: array, items: {type: object,
    properties: {...}}}`처럼 배열 안에 object가 중첩돼 있다. OpenAI strict 모드는
    "모든" object(중첩된 것 포함)에 additionalProperties=false + 그 object 자신의
    모든 필드를 required에 넣을 것을 요구한다 — 최상위만 변환하면 중첩된 tiers.items
    object가 이 조건을 못 만족해서 API가 400 Bad Request로 거부한다(실측: 동학이
    실제 키로 25문항 돌렸을 때 System B 75건 전부 이 이유로 실패한 것을 발견하고
    고쳤다)."""
    def convert_object(obj_schema: Dict[str, Any]) -> Dict[str, Any]:
        props = obj_schema.get("properties", {})
        required_original = set(obj_schema.get("required", []))
        new_props: Dict[str, Any] = {}
        for name, spec in props.items():
            new_props[name] = convert_value(spec, nullable=name not in required_original)
        return {
            "type": "object",
            "properties": new_props,
            "required": list(props.keys()),   # OpenAI strict 모드는 전부 required여야 함
            "additionalProperties": False,
        }

    def convert_value(spec: Dict[str, Any], nullable: bool) -> Dict[str, Any]:
        spec = dict(spec)
        t = spec.get("type")
        types = t if isinstance(t, list) else [t]
        if "object" in types and "properties" in spec:
            spec = convert_object(spec)
        elif "array" in types and isinstance(spec.get("items"), dict):
            # 배열 원소 자체는 "필수 아님"이라는 개념이 없다 — items는 항상 그대로,
            # 다만 items가 object면 그 내부도 재귀적으로 strict 조건을 채워야 한다.
            spec["items"] = convert_value(spec["items"], nullable=False)
        if nullable:
            cur_type = spec.get("type")
            if cur_type and "null" not in (cur_type if isinstance(cur_type, list) else [cur_type]):
                spec["type"] = [cur_type, "null"] if isinstance(cur_type, str) else list(cur_type) + ["null"]
        return spec

    return convert_object(schema)


def _call_openai(prompt: str, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """_call_gemini()와 동일한 계약(실패하면 예외 없이 None, 사유는 _LAST_ERROR에)을
    지키는 GPT(OpenAI) 버전. SDK 없이 표준 라이브러리 urllib만 쓴다(mvp/gemini_client.py
    /mvp/openai_client.py와 동일한 방식 — 이 파일만 별도 SDK를 새로 추가하지 않는다).

    2026-08-31 확정: AI_PROVIDER=openai일 때 이 함수가 **DEV25 공식 System B 경로**다
    (그 전까지는 실험용으로만 취급됐었다). AI_PROVIDER의 기본값은 여전히 "gemini"이므로
    이 함수는 명시적으로 `AI_PROVIDER=openai`를 지정했을 때만 _invoke()에서 대신
    불린다 — 아무도 안 건드리면 이 파일의 기존 동작(_call_gemini() 사용)은 그대로다."""
    global _LAST_ERROR
    key = os.environ.get(_OPENAI_API_KEY_ENV, "").strip()
    if not key:
        _LAST_ERROR = f"{_OPENAI_API_KEY_ENV} 미설정"
        return None
    import urllib.request
    import urllib.error
    try:
        body = {
            "model": _OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,                           # 재현성. 금융이라 창의성은 해롭다
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "extraction",
                    "schema": _gemini_schema_to_openai_strict(schema),
                    "strict": True,
                },
            },
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        text = raw["choices"][0]["message"]["content"]
        data = json.loads(text)
        _LAST_ERROR = None
        return data
    except urllib.error.HTTPError as e:
        # HTTPError.read()로 응답 본문을 읽어야 OpenAI가 실제로 왜 거부했는지(예:
        # 스키마 위반 상세 메시지) 남는다 — str(e)만 쓰면 "HTTP Error 400: Bad
        # Request"처럼 원인을 알 수 없는 문구만 남는다. 이 파일 상단 주석에 적힌
        # 2026-08-18 Gemini 404 사례("except가 삼키는 바람에 원인이 안 보였다")와
        # 똑같은 실패 패턴이라 동일한 원칙으로 고친다 — 조용히 삼키지 않는다.
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        _LAST_ERROR = f"HTTPError {e.code}: {body[:500] if body else str(e)}"
        return None
    except Exception as e:                                # 네트워크·쿼터·모델폐지·파싱 오류
        _LAST_ERROR = f"{type(e).__name__}: {str(e)[:200]}"
        return None


def _call_ai(prompt: str, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """AI_PROVIDER에 따라 _call_gemini()/_call_openai() 중 하나로 분기한다.
    기본값은 "gemini" — 아무도 AI_PROVIDER를 안 건드리면 이 함수는 항상
    _call_gemini()만 부르므로 기존 동작과 100% 동일하다."""
    if AI_PROVIDER == "openai":
        return _call_openai(prompt, schema)
    return _call_gemini(prompt, schema)


def _invoke(kind: str, payload: str, prompt: str,
            schema: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    """라이브 우선, 실패하면 캐시. 어느 쪽인지 반드시 표시한다.

    EVAL_STRICT=1(공식 평가모드)에서는 예외 — live가 실패하면 사유를 불문하고
    cache로 대체하지 않는다(SOURCE_RUN_FAILURE로 표시하고 None을 반환). 데모/개발
    모드(기본값)에서는 지금까지와 동일하게 cache를 안전망으로 쓴다."""
    live = _call_ai(prompt, schema)
    if live is not None:
        _write_cache(kind, payload, live)
        return live, SOURCE_LIVE
    if EVAL_STRICT:
        return None, SOURCE_RUN_FAILURE
    return _read_cache(kind, payload), SOURCE_CACHE


# ── 1단계 · 의미 유의성 판정 ────────────────────────────────────────────────
_MATERIALITY_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": [MATERIAL, COSMETIC]},
        "affected_field": {"type": "string"},
        "old_value": {"type": "string"},
        "new_value": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
}

_MATERIALITY_PROMPT = """당신은 금융 약관 변경을 검토하는 분석가입니다.

아래는 같은 조항의 변경 전후입니다. 이 변경이 **우대금리 계산 결과를 바꾸는지** 판정하세요.

MATERIAL — 계산 결과가 달라진다
  임계값·우대폭·기간·연산자·포함/제외 집합·귀속조건·예외 가 바뀐 경우
COSMETIC — 계산 결과가 같다
  띄어쓰기·조사·안내문구·단위표기·나열순서만 바뀐 경우

**숫자가 하나도 바뀌지 않아도 조건 구조가 바뀌면 MATERIAL입니다.**

[변경 전]
{before}

[변경 후]
{after}

affected_field 는 다음 중 하나로만 답하세요:
threshold, operator, window, effect_value, exception, attribution_rule,
inclusion_set, exclusion_set, cap, recalc_frequency, none
"""


def semantic_materiality(before: str, after: str) -> Materiality:
    """조항 변경이 계산에 영향을 주는지 판정한다."""
    payload = f"{before}||{after}"
    prompt = _MATERIALITY_PROMPT.format(before=before.strip(), after=after.strip())
    data, source = _invoke("materiality", payload, prompt, _MATERIALITY_SCHEMA)

    if not data:
        # 캐시도 없고 라이브도 안 되면 판정하지 않는다.
        # 모르는 상태에서 COSMETIC이라고 답하면 위험한 변경을 통과시킨다.
        return Materiality(
            verdict=MATERIAL,
            affected_field=None, old_value=None, new_value=None,
            reason="AI 판정을 얻지 못했습니다. 안전한 쪽(MATERIAL)으로 두고 사람 검토로 넘깁니다.",
            source=SOURCE_CACHE, model="(미실행)",
        )

    verdict = data.get("verdict")
    if verdict not in (MATERIAL, COSMETIC):
        verdict = MATERIAL
    af = data.get("affected_field")
    return Materiality(
        verdict=verdict,
        affected_field=None if af in ("none", "", None) else af,
        old_value=data.get("old_value") or None,
        new_value=data.get("new_value") or None,
        reason=data.get("reason", ""),
        source=source,
        model=_active_model_name() if source == SOURCE_LIVE else f"{_active_model_name()} (캐시)",
    )


# ── 2단계 · 규칙 컴파일 ─────────────────────────────────────────────────────
_COMPILE_SCHEMA = {
    "type": "object",
    "properties": {
        "threshold": {"type": "number"},
        "operator": {"type": "string"},
        "window": {"type": "string"},
        "effect_value": {"type": "number"},
        "exception": {"type": "string"},
        "attribution_rule": {"type": "string"},
    },
    "required": ["operator"],
}

_COMPILE_PROMPT = """당신은 금융 약관 조항을 계산 가능한 규칙으로 옮기는 컴파일러입니다.

아래 조항에서 다음 6개만 추출하세요.

threshold         조건을 만족하는 기준 수치. 원 단위 정수로. (예: 600000)
operator          비교 연산자. >= > <= < 중 하나. 조항이 "이상"이면 >=, "초과"면 >
window            측정 기간. (예: 3M, 1M, 없으면 빈 문자열)
effect_value      우대폭. %p 단위 숫자만. (예: 0.2)
exception         적용에서 제외되는 경우를 조항 표현 그대로. 없으면 빈 문자열
attribution_rule  실적이 인정되기 위한 귀속조건. 없으면 빈 문자열

**절대 규칙**

1. 조항에 없는 숫자를 만들지 마세요. 확실하지 않으면 그 필드를 비우세요.
2. 추론하지 마세요. 조항에 쓰인 것만 옮기세요.
3. "60만원"은 600000으로, "연 0.2%p"는 0.2로 적으세요.
4. exception 과 attribution_rule 은 조항 표현을 최대한 그대로 쓰세요.

[조항]
{clause}
"""


def compile_rule(clause_text: str) -> RuleCandidate:
    """조항 하나를 타입 있는 규칙 후보로 만든다. 아직 엔진에 못 들어간다."""
    prompt = _COMPILE_PROMPT.format(clause=clause_text.strip())
    data, source = _invoke("compile", clause_text, prompt, _COMPILE_SCHEMA)

    fields: Dict[str, Any] = {}
    if data:
        for k in COMPILED_FIELDS:
            v = data.get(k)
            if v in (None, ""):
                continue
            # 구조화 출력은 숫자 필드를 비워두지 못하고 0을 채운다.
            # 약관에서 임계값 0원·우대폭 0%p는 의미가 없으므로 '추출 안 됨'으로 본다.
            # 이걸 안 거르면 0이 근거 문장에 없다는 이유로 환각 게이트가 잘못 울린다.
            if k in ("threshold", "effect_value"):
                try:
                    if float(v) == 0.0:
                        continue
                except (TypeError, ValueError):
                    pass
            fields[k] = v

    cand = RuleCandidate(
        fields=fields,
        evidence_span=clause_text.strip(),
        clause_hash=clause_hash(clause_text),
        source=source,
        model=_active_model_name() if source == SOURCE_LIVE else f"{_active_model_name()} (캐시)",
    )
    cand.gates = run_gates(cand, expected_hash=cand.clause_hash)
    if not cand.all_passed:
        cand.status = REJECTED
    return cand


# ── 3단계 · 기계 검증 게이트 ────────────────────────────────────────────────
def run_gates(cand: RuleCandidate, expected_hash: Optional[str] = None) -> List[Gate]:
    """사람에게 보이기 전에 기계가 먼저 거른다.

    사람 승인은 마지막 관문이지 첫 관문이 아니다.
    기계가 걸러낼 수 있는 건 사람에게 올리지 않는다.
    """
    gates: List[Gate] = []
    f = cand.fields

    # 1 — 뭐라도 뽑혔는가
    gates.append(Gate(
        "추출 성공",
        bool(f),
        f"{len(f)}개 필드 추출" if f else "추출된 필드가 없습니다",
    ))

    # 2 — 스키마: 알려진 필드만
    unknown = sorted(set(f) - set(COMPILED_FIELDS))
    gates.append(Gate(
        "스키마 적합",
        not unknown,
        "정의된 필드만 사용" if not unknown else f"알 수 없는 필드: {unknown}",
    ))

    # 3 — 연산자 유효성
    op = f.get("operator")
    if op is None:
        gates.append(Gate("연산자 유효", True, "연산자 없음 (해당 없음)"))
    else:
        gates.append(Gate(
            "연산자 유효",
            op in _ALLOWED_OPERATORS,
            f"'{op}'" if op in _ALLOWED_OPERATORS else f"허용되지 않는 연산자: '{op}'",
        ))

    # 4 — 연산자가 근거 표현과 맞는가 ("이상"이면 >=, "초과"면 >)
    ev = _normalize(cand.evidence_span)
    if op in (">=", ">"):
        has_isang, has_choqua = "이상" in ev, "초과" in ev
        if has_isang or has_choqua:
            want = ">=" if has_isang else ">"
            gates.append(Gate(
                "연산자 ↔ 근거 일치",
                op == want,
                f"근거에 '{'이상' if has_isang else '초과'}' → {want} 기대, 실제 {op}",
            ))
        else:
            gates.append(Gate("연산자 ↔ 근거 일치", True, "근거에 이상/초과 표현 없음"))
    else:
        gates.append(Gate("연산자 ↔ 근거 일치", True, "해당 없음"))

    # 5 — 조항 해시 일치
    actual = clause_hash(cand.evidence_span)
    ok_hash = (expected_hash is None) or (actual == expected_hash)
    gates.append(Gate(
        "조항 해시 일치",
        ok_hash,
        f"{actual[:16]}…" if ok_hash else f"불일치 {actual[:16]}… ≠ {str(expected_hash)[:16]}…",
    ))

    # 6 — 숫자 접지 【환각 방어의 핵심】
    bad = ungrounded_numbers(f, cand.evidence_span)
    gates.append(Gate(
        "숫자가 근거에 실재",
        not bad,
        "모든 숫자가 근거 문장에 있습니다" if not bad
        else "근거에 없는 숫자: " + ", ".join(f"{k}={v:g}" for k, v in bad),
    ))

    # 7 — 서술 필드 접지
    ungrounded = [k for k in ("exception", "attribution_rule")
                  if k in f and not _span_grounded(f[k], cand.evidence_span)]
    gates.append(Gate(
        "서술이 근거에서 유래",
        not ungrounded,
        "근거 문장에서 확인됨" if not ungrounded
        else f"근거에서 확인 불가: {ungrounded}",
    ))

    # 8 — 미해결 예외가 남아 있지 않은가
    has_exception_marker = any(m in ev for m in ("다만", "제외", "예외", "단,"))
    resolved = "exception" in f and bool(str(f.get("exception", "")).strip())
    gates.append(Gate(
        "예외 누락 없음",
        (not has_exception_marker) or resolved,
        "예외 표현 없음" if not has_exception_marker
        else ("예외를 추출함" if resolved
              else "근거에 예외 표현이 있는데 추출되지 않았습니다"),
    ))

    return gates


# ── 4단계 · 사람 승인 ───────────────────────────────────────────────────────
def approve(cand: RuleCandidate, approver: str) -> RuleCandidate:
    """사람이 승인해야만 VERIFIED가 된다.

    기계 게이트를 전부 통과해도 사람 승인 없이는 엔진에 들어가지 않는다.
    금소법 방어선이 여기 있다 — 최종 책임 주체가 사람이다.
    """
    if not cand.all_passed:
        raise ValueError("기계 검증을 통과하지 못한 후보는 승인할 수 없습니다.")
    if not (approver or "").strip():
        raise ValueError("승인자를 기록해야 합니다.")
    cand.status = VERIFIED
    return cand


# ── 파이프라인 ──────────────────────────────────────────────────────────────
def pipeline(before: str, after: str) -> Dict[str, Any]:
    """약관 변경 하나를 끝까지 흘려보낸다. 각 단계 결과를 전부 돌려준다.

    화면이 이걸 그대로 그리면 'AI가 왜 필요한지'가 30초에 보인다.
    """
    hash_changed = clause_hash(before) != clause_hash(after)
    mat = semantic_materiality(before, after)

    stages: Dict[str, Any] = {
        "change_detection": {
            "hash_before": clause_hash(before)[:16],
            "hash_after": clause_hash(after)[:16],
            "changed": hash_changed,
            "note": "해시는 '바뀌었다'까지만 안다. 계산에 영향을 주는지는 모른다.",
        },
        "materiality": mat.to_dict(),
        "freshness": None,
        "candidate": None,
        "engine_ready": False,
    }

    if not hash_changed:
        stages["freshness"] = {"status": "FRESH", "note": "조항이 바뀌지 않았습니다."}
        stages["engine_ready"] = True
        return stages

    if mat.verdict == COSMETIC:
        stages["freshness"] = {
            "status": "FRESH",
            "note": "표현만 바뀌었습니다. 근거 해시만 갱신하고 기존 규칙을 유지합니다.",
        }
        stages["engine_ready"] = True
        return stages

    # MATERIAL — 계산을 멈춘다.
    stages["freshness"] = {
        "status": "STALE_REVIEW",
        "note": "계산에 영향을 주는 변경입니다. 사람이 승인할 때까지 판정을 멈춥니다.",
    }
    cand = compile_rule(after)
    stages["candidate"] = cand.to_dict()
    stages["engine_ready"] = False
    return stages


__all__ = [
    "MATERIAL", "COSMETIC", "CANDIDATE", "VERIFIED", "REJECTED",
    "Gate", "Materiality", "RuleCandidate",
    "semantic_materiality", "compile_rule", "run_gates", "approve", "pipeline",
    "ungrounded_numbers", "number_surface_forms", "clause_hash",
    "api_key_present", "sdk_present", "live_status", "last_error",
]
