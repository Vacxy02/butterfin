"""
OpenAI(GPT) 호출 공통 헬퍼. gemini_client.py와 정확히 같은 인터페이스
(call_openai_json / has_api_key / OpenAIError)를 맞춰서, action_interpreter.py가
AI_PROVIDER 환경변수 하나로 Gemini↔GPT를 바꿔 낄 수 있게 한다.

- OPENAI_API_KEY가 없으면 자동으로 mock 모드로 동작한다 (API 실패로 서비스가 멈추지 않게).
- 키를 코드에 하드코딩하지 않는다. 환경변수에서만 읽는다.
- 모델명은 OPENAI_MODEL 환경변수로 바꿀 수 있다(기본 gpt-4o-mini).

2026-08-30: "GEMINI_API_KEY 대신 GPT API를 쓰면 쉬운가" 질문에 대한 답으로 추가.
DEV25 System B/C(ablation/wide_compiler.py → mvp/ai_rule.py)는 여기 포함하지 않는다 —
그쪽 B 프롬프트는 이미 Gemini 기준으로 팀이 확정한 것이라(08_DEV25_보호규칙 §2),
모델을 바꾸면 그 확정 자체가 무효가 되므로 박승렬 확인 없이는 손대지 않는다. 이
파일은 라이브 데모(action_interpreter.py의 문장 해석)에만 쓴다.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from typing import Optional, Dict, Any

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


class OpenAIError(Exception):
    pass


def has_api_key() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def call_openai_json(system_prompt: str, user_text: str, *, temperature: float = 0.0,
                      model: Optional[str] = None, timeout: float = 20.0) -> Dict[str, Any]:
    """OpenAI Chat Completions를 호출해 JSON 응답을 파싱해서 반환한다.
    실패(키 없음/HTTP 오류/JSON 파싱 실패)는 OpenAIError로 던진다 — gemini_client.
    call_gemini_json()과 동일하게, 호출자가 NEED_INFO/REVIEW/HOLD 계열 fail-safe로
    처리한다(AI가 직접 최종 판정하지 않는다는 원칙은 그대로 유지)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise OpenAIError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

    mdl = model or DEFAULT_MODEL
    url = "https://api.openai.com/v1/chat/completions"
    body = {
        "model": mdl,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": temperature,
        # Gemini의 responseMimeType=application/json과 동급 — "반드시 JSON 객체로만
        # 답하라"는 강제. (더 엄격한 response_format=json_schema도 있지만, 여기서는
        # gemini_client.py와 대응되는 최소 계약만 맞춘다 — 스키마 자체는 SYSTEM_PROMPT
        # 문구로 이미 지시하고 있고, 최종 검증은 어차피 _double_check()가 한다.)
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise OpenAIError(f"OpenAI 호출 실패: {e}") from e
    latency_ms = int((time.time() - t0) * 1000)

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise OpenAIError(f"OpenAI 응답 형식이 예상과 다릅니다: {data}") from e

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise OpenAIError(f"JSON_PARSE_FAILURE: {e} — raw={text[:300]}") from e

    return {"parsed": parsed, "raw_text": text, "model": mdl, "latency_ms": latency_ms}
