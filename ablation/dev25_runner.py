# -*- coding: utf-8 -*-
"""
DEV25 실행기 — blind25_samples.json의 25건을 A(1회)/B(3회)/C(3회)=175행 실행.

2026-08-27 재작성 (박승렬 지시 반영):
  System A  StrongRegexBaseline.extract()   (blind25_fixed.py) — 결정론적, 1회
  Gate      EvidenceGate.verify()           (blind25_fixed.py) — ai_rule.ungrounded_numbers 기반
  System B  wide_compiler.compile_raw()     — Gemini 호출, Gate 없음, 3회
  System C  wide_compiler.gate_only()       — **Gemini를 다시 호출하지 않는다.**
            System B의 3회 결과(raw/parsed)를 그대로 재사용해서 Gate만 적용한다.
            이 파일의 _row_from_c()가 그 조립을 담당한다 — wide_compiler.compile_with_gate()
            (내부적으로 Gemini를 새로 호출하는 편의 함수)는 여기서 절대 쓰지 않는다.

RUN_RULES 준수:
  - 25건 실행 끝날 때까지 baseline_regex/ai_rule/blind25_fixed 수정 금지 (이 스크립트 실행
    중에는 아무 것도 수정하지 않는다 — 코드 수정은 스크립트 밖, 실행 전/후에만 한다)
  - sample_id별 예외코드 없음 (전부 동일한 extract()/compile_raw()/gate_only() 호출)
  - Gold로 채점하지 않는다 (이 스크립트는 GOLD 파일을 열지도, 참조하지도 않는다)
  - 결과 필드(OUTPUT_COLUMNS): sample_id, system, run_id, model_name, prompt_version,
    raw_output_json, parsed_output_json, schema_valid, accepted, reject_reason,
    http_status, retry_count, latency_ms, error_log, reused_from_run
  - retry는 429/5xx/timeout일 때만 한다(wide_compiler._is_retryable) — "답이 마음에
    안 들어서" 다시 부르는 재시도는 없다. 유효한 응답이 한 번 나오면 그대로 최종값이다.
  - cache/checkpoint: 문항×System×run 단위로 dev25_checkpoint.jsonl에 즉시 기록한다.
    중간에 API 오류로 죽어도 재실행 시 이미 끝난 조합은 다시 부르지 않고 파일에서
    읽어온다 — 처음부터 다시 돌 필요가 없다. run(resume=False)로 끄고 완전히 새로
    돌릴 수도 있다.

주의: GEMINI_API_KEY가 없으면 B/C는 정직하게 "추출 실패"로 채워진다 (ai_rule.py와 같은
원칙 — 키가 없다고 그럴듯한 가짜 값을 지어내지 않는다). 이 경우 175행은 "파이프라인이
기계적으로 175행을 만들어내는지"만 검증한 것이지, 실제 Gemini 성능 비교가 아니다.
실제 키로 반드시 재실행해야 진짜 DEV25 결과가 된다 (PROJECT_CURRENT_STATE.md §6).
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Callable, Dict, Optional, Tuple

ROOT = os.environ.get("AR_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "mvp"))
sys.path.insert(0, os.path.join(ROOT, "ablation"))

import ai_rule
from blind25_fixed import StrongRegexBaseline, EvidenceGate
import wide_compiler

SAMPLES_PATH = os.path.join(os.path.dirname(__file__), "blind25_samples.json")
CHECKPOINT_PATH = os.path.join(os.path.dirname(__file__), "dev25_checkpoint.jsonl")

OUTPUT_COLUMNS = [
    "sample_id", "system", "run_id", "model_name", "prompt_version",
    "raw_output_json", "parsed_output_json", "schema_valid",
    "accepted", "reject_reason", "http_status", "retry_count",
    "latency_ms", "error_log", "reused_from_run",
]


def load_samples():
    with open(SAMPLES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# 2026-08-26 실측: 150번(B 75 + C였던 것 75)의 Gemini 호출을 쉬지 않고 쏘면 무료 등급
# 분당 요청 한도(429 RESOURCE_EXHAUSTED)에 걸려 초반 몇 건만 성공한다. 지금은 C가
# Gemini를 안 부르므로 실제 호출은 B의 75회뿐이지만, 간격 로직은 그대로 둔다.
_CALL_SPACING_SECONDS = 2.0


# ── checkpoint(캐시) ─────────────────────────────────────────────────────
def _row_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return (row["sample_id"], row["system"], row["run_id"])


def _load_checkpoint(path: str) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    done: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    if not os.path.exists(path):
        return done
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # 중간에 잘린 마지막 줄 등 — 손상된 줄은 버리고 계속 읽는다
            done[_row_key(row)] = row
    return done


def _append_checkpoint(path: str, row: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ── 행 조립 ───────────────────────────────────────────────────────────────
def _row_from_a(sid: str, fields: Dict[str, Any], verdict: Dict[str, Any], latency_ms: int) -> Dict[str, Any]:
    return {
        "sample_id": sid, "system": "A", "run_id": "run_1",
        "model_name": StrongRegexBaseline.VERSION, "prompt_version": None,
        "raw_output_json": json.dumps(fields, ensure_ascii=False),
        "parsed_output_json": json.dumps(fields, ensure_ascii=False),
        "schema_valid": None,  # 정규식 결과는 애초에 Gemini 스키마 검증 대상이 아님
        "accepted": "Y" if verdict["accepted"] else "N",
        "reject_reason": verdict["reject_reason"],
        "http_status": None, "retry_count": 0, "latency_ms": latency_ms,
        "error_log": json.dumps([], ensure_ascii=False),
        "reused_from_run": None,
    }


def _row_from_b(sid: str, run_id: str, fields: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sample_id": sid, "system": "B", "run_id": run_id,
        "model_name": meta["model_name"], "prompt_version": meta["prompt_version"],
        "raw_output_json": json.dumps(meta["raw_output_json"], ensure_ascii=False),
        "parsed_output_json": json.dumps(fields, ensure_ascii=False),
        "schema_valid": meta["schema_valid"],
        "accepted": meta["accepted"], "reject_reason": meta["reject_reason"],
        "http_status": meta["http_status"], "retry_count": meta["retry_count"],
        "latency_ms": meta["latency_ms"],
        "error_log": json.dumps(meta["error_log"], ensure_ascii=False),
        "reused_from_run": None,
    }


def _row_from_c(sid: str, run_id: str, b_row: Dict[str, Any], source_text: str) -> Dict[str, Any]:
    """System C: B의 결과를 그대로 재사용한다 — 여기서 Gemini를 부르는 코드는 없다."""
    if b_row["accepted"] == "N":
        # B가 이미 실패면 Gate를 적용할 대상 자체가 없다 — B의 실패를 그대로 이어받는다.
        return {
            "sample_id": sid, "system": "C", "run_id": run_id,
            "model_name": b_row["model_name"], "prompt_version": b_row["prompt_version"],
            "raw_output_json": b_row["raw_output_json"],
            "parsed_output_json": b_row["parsed_output_json"],
            "schema_valid": b_row["schema_valid"],
            "accepted": "N",
            "reject_reason": f"B 추출 실패로 Gate 적용 대상 없음 (B 사유: {b_row['reject_reason']})",
            "http_status": None,  # C는 API를 호출하지 않았다
            "retry_count": 0,
            "latency_ms": 0,
            "error_log": b_row["error_log"],
            "reused_from_run": b_row["run_id"],
        }

    b_fields = json.loads(b_row["parsed_output_json"]) if b_row["parsed_output_json"] else {}
    accepted, reject_reason, gate_latency_ms = wide_compiler.gate_only(b_fields, source_text)
    return {
        "sample_id": sid, "system": "C", "run_id": run_id,
        "model_name": b_row["model_name"], "prompt_version": b_row["prompt_version"],
        "raw_output_json": b_row["raw_output_json"],       # B가 받은 원본 그대로, 재요청 없음
        "parsed_output_json": b_row["parsed_output_json"], # B가 뽑은 필드 그대로, Gate는 값을 바꾸지 않음
        "schema_valid": b_row["schema_valid"],
        "accepted": accepted, "reject_reason": reject_reason,
        "http_status": None,   # C는 Gemini/HTTP를 호출하지 않았다
        "retry_count": 0,      # 호출이 없으니 재시도도 없다
        "latency_ms": gate_latency_ms,  # Gate 검증에만 걸린 시간 (B의 호출 시간과 별개)
        "error_log": json.dumps([], ensure_ascii=False),
        "reused_from_run": b_row["run_id"],  # C가 어느 B 실행을 재사용했는지 감사 추적용
    }


def _compute_a(text: str, sid: str) -> Dict[str, Any]:
    t0 = time.time()
    fields = StrongRegexBaseline.extract(text)
    latency = int((time.time() - t0) * 1000)
    verdict = EvidenceGate.verify(fields, text)
    return _row_from_a(sid, fields, verdict, latency)


def _compute_b(text: str, sid: str, run_id: str) -> Dict[str, Any]:
    fields, meta = wide_compiler.compile_raw(text, rule_id=sid)
    return _row_from_b(sid, run_id, fields, meta)


def run(out_path: Optional[str] = None, checkpoint_path: Optional[str] = None,
        resume: bool = True) -> tuple:
    """25문항을 A/B/C로 실행해 175행을 만든다.

    resume=True(기본값)면 checkpoint_path(기본 dev25_checkpoint.jsonl)에 이미 저장된
    (sample_id, system, run_id) 조합은 다시 계산하지 않고 그대로 읽어 쓴다 — 중간에
    API 오류로 죽었어도 처음부터 다시 돌 필요가 없다. resume=False면 기존 checkpoint
    파일을 지우고 완전히 새로 돈다.
    """
    samples = load_samples()
    checkpoint_path = checkpoint_path or CHECKPOINT_PATH

    if not resume and os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)
    done = _load_checkpoint(checkpoint_path) if resume else {}

    rows = []
    is_mock = not ai_rule.live_status()["ready"]

    def _get_or_compute(key: Tuple[str, str, str], compute_fn: Callable[[], Dict[str, Any]]) -> Tuple[Dict[str, Any], bool]:
        if key in done:
            return done[key], True
        row = compute_fn()
        done[key] = row
        _append_checkpoint(checkpoint_path, row)
        return row, False

    for s in samples:
        sid = s["sample_id"]
        text = s["source_bundle_text"]

        # System A — Regex baseline, 1회 (결정론적, LLM 없음, 재시도/캐시 의미 없음)
        a_row, _ = _get_or_compute((sid, "A", "run_1"), lambda: _compute_a(text, sid))
        rows.append(a_row)

        # System B — Gemini 넓은 스키마, Gate 없음, 3회
        b_rows = []
        for i in range(1, 4):
            run_id = f"run_{i}"
            b_row, cached = _get_or_compute((sid, "B", run_id), lambda: _compute_b(text, sid, run_id))
            rows.append(b_row)
            b_rows.append(b_row)
            if not is_mock and not cached:
                time.sleep(_CALL_SPACING_SECONDS)

        # System C — Gemini 재호출 없음, B의 3회 결과를 그대로 재사용해 Gate만 적용
        for i in range(1, 4):
            run_id = f"run_{i}"
            b_row = b_rows[i - 1]
            c_row, _ = _get_or_compute((sid, "C", run_id), lambda: _row_from_c(sid, run_id, b_row, text))
            rows.append(c_row)

    assert len(rows) == 175, f"175행이어야 하는데 {len(rows)}행 나옴"

    if out_path:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "DEV25_RESULTS"
        ws.append(OUTPUT_COLUMNS)
        for r in rows:
            ws.append([r[c] for c in OUTPUT_COLUMNS])
        wb.save(out_path)

    return rows, is_mock


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DEV25 A/B/C 25문항 runner")
    parser.add_argument("--fresh", action="store_true",
                         help="checkpoint를 지우고 처음부터 다시 돈다 (기본은 이어서 재개)")
    args = parser.parse_args()

    out = os.path.join(os.path.dirname(__file__), "DEV25_RESULTS.xlsx")
    rows, is_mock = run(out_path=out, resume=not args.fresh)
    a_rows = [r for r in rows if r["system"] == "A"]
    b_rows = [r for r in rows if r["system"] == "B"]
    c_rows = [r for r in rows if r["system"] == "C"]
    print(f"총 {len(rows)}행 생성 ({'GEMINI_API_KEY 없음 — B/C는 정직하게 추출 실패로 채워짐' if is_mock else '실제 Gemini 사용'})")
    print(f"A: {len(a_rows)}행, accepted=Y {sum(1 for r in a_rows if r['accepted']=='Y')}")
    print(f"B: {len(b_rows)}행, accepted=Y {sum(1 for r in b_rows if r['accepted']=='Y')}, "
          f"재시도 총합 {sum(r['retry_count'] for r in b_rows)}")
    print(f"C: {len(c_rows)}행, accepted=Y {sum(1 for r in c_rows if r['accepted']=='Y')}, "
          f"Gemini 재호출 0회 (전부 reused_from_run 있음: {all(r['reused_from_run'] for r in c_rows)})")
    print(f"저장: {out}")
    print(f"checkpoint: {CHECKPOINT_PATH}")
