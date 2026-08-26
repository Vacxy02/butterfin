# -*- coding: utf-8 -*-
"""
DEV25 실행기 — blind25_samples.json의 25건을 A(1회)/B(3회)/C(3회)=175행 실행.

2026-08-25 재작성: 팀의 실제 파일(ai_rule.py / baseline_regex.py / blind25_fixed.py)이
도착해서 이 스크립트가 그것들을 쓰도록 다시 짰다. 이전 버전은 이 세션에서 임시로 만든
mvp/rule_compiler.py(CandidateRule 16필드) 기반이었는데, 이제는 팀의 실제
ExtendedRuleSchema(14필드) 기반으로 맞춘다.

  System A  StrongRegexBaseline.extract()   (blind25_fixed.py) — 결정론적, 1회
  Gate      EvidenceGate.verify()           (blind25_fixed.py) — ai_rule.ungrounded_numbers 기반
  System B  wide_compiler.compile_raw()     (이 세션에서 새로 작성) — Gemini, Gate 없음, 3회
  System C  wide_compiler.compile_with_gate()                    — B + Gate, 3회

RUN_RULES 준수:
  - 25건 실행 끝날 때까지 baseline_regex/ai_rule/blind25_fixed 수정 금지 (이 스크립트 실행
    중에는 아무 것도 수정하지 않는다 — 코드 수정은 스크립트 밖, 실행 전/후에만 한다)
  - sample_id별 예외코드 없음 (전부 동일한 extract()/compile_raw()/compile_with_gate() 호출)
  - Gold로 채점하지 않는다 (이 스크립트는 GOLD 파일을 열지도, 참조하지도 않는다)
  - 결과 필드: sample_id, system, run_id, model_name, prompt_version, raw_output_json,
    parsed_output_json, accepted, reject_reason, latency_ms

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

ROOT = os.environ.get("AR_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "mvp"))
sys.path.insert(0, os.path.join(ROOT, "ablation"))

import ai_rule
from blind25_fixed import StrongRegexBaseline, EvidenceGate
import wide_compiler

SAMPLES_PATH = os.path.join(os.path.dirname(__file__), "blind25_samples.json")


def load_samples():
    with open(SAMPLES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run(out_path: str = None) -> tuple:
    samples = load_samples()
    rows = []
    is_mock = not ai_rule.live_status()["ready"]

    for s in samples:
        sid = s["sample_id"]
        text = s["source_bundle_text"]

        # System A — Regex baseline, 1회 (결정론적, LLM 없음)
        t0 = time.time()
        a_fields = StrongRegexBaseline.extract(text)
        a_latency = int((time.time() - t0) * 1000)
        a_verdict = EvidenceGate.verify(a_fields, text)
        rows.append({
            "sample_id": sid, "system": "A", "run_id": "run_1",
            "model_name": StrongRegexBaseline.VERSION, "prompt_version": None,
            "raw_output_json": json.dumps(a_fields, ensure_ascii=False),
            "parsed_output_json": json.dumps(a_fields, ensure_ascii=False),
            "accepted": "Y" if a_verdict["accepted"] else "N",
            "reject_reason": a_verdict["reject_reason"],
            "latency_ms": a_latency,
        })

        # System B — Gemini 넓은 스키마, Gate 없음, 3회
        for i in range(1, 4):
            fields, meta = wide_compiler.compile_raw(text, rule_id=sid)
            rows.append({
                "sample_id": sid, "system": "B", "run_id": f"run_{i}",
                "model_name": meta["model_name"], "prompt_version": meta["prompt_version"],
                "raw_output_json": json.dumps(meta["raw_output_json"], ensure_ascii=False),
                "parsed_output_json": json.dumps(fields, ensure_ascii=False),
                "accepted": meta["accepted"], "reject_reason": meta["reject_reason"],
                "latency_ms": meta["latency_ms"],
            })

        # System C — Gemini + Evidence/Schema Gate, 3회
        for i in range(1, 4):
            fields, meta = wide_compiler.compile_with_gate(text, rule_id=sid)
            rows.append({
                "sample_id": sid, "system": "C", "run_id": f"run_{i}",
                "model_name": meta["model_name"], "prompt_version": meta["prompt_version"],
                "raw_output_json": json.dumps(meta["raw_output_json"], ensure_ascii=False),
                "parsed_output_json": json.dumps(fields, ensure_ascii=False),
                "accepted": meta["accepted"], "reject_reason": meta["reject_reason"],
                "latency_ms": meta["latency_ms"],
            })

    assert len(rows) == 175, f"175행이어야 하는데 {len(rows)}행 나옴"

    if out_path:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "DEV25_RESULTS"
        cols = ["sample_id", "system", "run_id", "model_name", "prompt_version",
                "raw_output_json", "parsed_output_json", "accepted", "reject_reason", "latency_ms"]
        ws.append(cols)
        for r in rows:
            ws.append([r[c] for c in cols])
        wb.save(out_path)

    return rows, is_mock


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "DEV25_RESULTS.xlsx")
    rows, is_mock = run(out_path=out)
    a_rows = [r for r in rows if r["system"] == "A"]
    b_rows = [r for r in rows if r["system"] == "B"]
    c_rows = [r for r in rows if r["system"] == "C"]
    print(f"총 {len(rows)}행 생성 ({'GEMINI_API_KEY 없음 — B/C는 정직하게 추출 실패로 채워짐' if is_mock else '실제 Gemini 사용'})")
    print(f"A: {len(a_rows)}행, accepted=Y {sum(1 for r in a_rows if r['accepted']=='Y')}")
    print(f"B: {len(b_rows)}행, accepted=Y {sum(1 for r in b_rows if r['accepted']=='Y')}")
    print(f"C: {len(c_rows)}행, accepted=Y {sum(1 for r in c_rows if r['accepted']=='Y')}")
    print(f"저장: {out}")
