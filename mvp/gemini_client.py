"""
Gemini 호출 공통 헬퍼. action_interpreter.py(라이브 데모의 자연어 행동 해석)가 쓴다.

(2026-08-25: 예전에는 mvp/rule_compiler.py도 같이 썼지만, 팀의 실제 ai_rule.py가
도착하면서 rule_compiler.py는 폐기했다. DEV25 System B/C의 약관 컴파일은 이제
ablation/wide_compiler.py가 맡고, 그쪽은 이 REST 헬퍼가 아니라 ai_rule.py 자체의
google.genai SDK 호출·캐시 경로(ai_rule._invoke)를 재사용한다 — 두 호출 경로를
따로 유지하는 게 아니라 팀이 이미 검증한 쪽에 맞춘 것이다.)

- GEMINI_API_KEY가 없으면 자동으로 mock 모드로 동작한다 (API 실패로 서비스가 멈추지 않게).
- 키를 코드에 하드코딩하지 않는다. 환경변수에서만 읽는다.
- 모델명은 GEMINI_MODEL 환경변수로 바꿀 수 있다.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from typing import Optional, Dict, Any

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


class GeminiError(Exception):
    pass


def has_api_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def call_gemini_json(system_prompt: str, user_text: str, *, temperature: float = 0.0,
                      model: Optional[str] = None, timeout: float = 20.0) -> Dict[str, Any]:
    """Gemini generateContent를 호출해 JSON 응답을 파싱해서 반환한다.
    실패(키 없음/HTTP 오류/JSON 파싱 실패)는 GeminiError로 던진다 — 호출자가
    NEED_INFO/REVIEW/HOLD 계열 fail-safe로 처리한다 (AI가 직접 최종 판정하지 않는다)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError("GEMINI_API_KEY가 설정되어 있지 않습니다.")

    mdl = model or DEFAULT_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent?key={api_key}"
    body = {
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise GeminiError(f"Gemini 호출 실패: {e}") from e
    latency_ms = int((time.time() - t0) * 1000)

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise GeminiError(f"Gemini 응답 형식이 예상과 다릅니다: {data}") from e

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise GeminiError(f"JSON_PARSE_FAILURE: {e} — raw={text[:300]}") from e

    return {"parsed": parsed, "raw_text": text, "model": mdl, "latency_ms": latency_ms}
