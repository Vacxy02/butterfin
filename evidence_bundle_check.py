# -*- coding: utf-8 -*-
"""Evidence Bundle 접지 검사기 — 역할 C 완료 판정용.

원장(action_reversal_rule_ledger_v3.csv)의 숫자 필드(threshold · effect_value)가
**자기 근거 원문 안에 글자로 존재하는지** 검사한다.

근거 원문 = 원장의 evidence_span + 번들(evidence_bundle_*.csv)의 rate_evidence_span.

분류
  실수치   조항이 실제로 적은 금액·회차·우대폭 — 근거에 있어야 한다
  센티넬   조건을 숫자로 인코딩한 값(0=미보유, 1=참, 0.6667=2/3) — 검사 제외
  (없음)   필드 자체가 비어 있음 — 검사 대상 아님

    python evidence_bundle_check.py
"""

from __future__ import annotations

import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "mvp"))

from ai_rule import number_surface_forms, _normalize, _span_grounded  # noqa: E402

LEDGER = os.path.join(HERE, "action_reversal_rule_ledger_v3.csv")
BUNDLE = os.path.join(HERE, "evidence_bundle_2026-08-21.csv")

SENTINELS = {0.0, 1.0, 0.6667}


def grounded(value: float, haystack: str) -> bool:
    hay = _normalize(haystack)
    return any(_normalize(f) in hay for f in number_surface_forms(value))


def main() -> int:
    ledger = list(csv.DictReader(io.open(LEDGER, encoding="utf-8")))
    bundle = {r["rule_id"]: r for r in csv.DictReader(io.open(BUNDLE, encoding="utf-8-sig"))}

    print(f"원장 {len(ledger)}행 · 번들 {len(bundle)}행\n")
    missing_bundle = [r["rule_id"] for r in ledger if r["rule_id"] not in bundle]
    if missing_bundle:
        print(f"⚠ 번들에 없는 규칙: {missing_bundle}\n")

    tot = hit = 0
    fails = []
    print(f"{'rule_id':30s} {'threshold':>10s} {'우대폭':>8s}")
    for r in ledger:
        b = bundle.get(r["rule_id"], {})
        ev = r["evidence_span"] + " " + b.get("rate_evidence_span", "")
        marks = []
        for k in ("threshold", "effect_value"):
            v = r[k].strip()
            if not v:
                marks.append("(없음)")
                continue
            try:
                fv = float(v)
            except ValueError:
                marks.append("(문자)")
                continue
            if k == "threshold" and round(fv, 4) in SENTINELS:
                marks.append("센티넬")
                continue
            tot += 1
            if grounded(fv, ev):
                hit += 1
                marks.append("OK")
            else:
                marks.append("★누락")
                fails.append((r["rule_id"], k, fv))
        print(f"{r['rule_id']:30s} {marks[0]:>10s} {marks[1]:>8s}")

    print(f"\n[A] 금액·우대폭 접지: {hit}/{tot} ({hit / tot:.0%})" if tot else "검사 대상 없음")

    # ── [B] 나머지 활성 필드 ──────────────────────────────────────────────
    # 금액·우대폭만 검사하면 "접지 100%"가 실제보다 넓게 들린다.
    # 판정에 쓰이는 다른 필드(측정기간·상한·귀속·제외집합)도 근거에 있어야
    # "이 값 어디서 났나"에 전건 답할 수 있다.
    import re as _re
    b_tot = b_hit = 0
    b_fails = []
    for r in ledger:
        b = bundle.get(r["rule_id"], {})
        ev = r["evidence_span"] + " " + b.get("rate_evidence_span", "")
        ev_nums = set(_re.findall(r"\d+", _normalize(ev)))

        w = r.get("window", "").strip()
        if w and w != "POINT":
            m = _re.match(r"(\d+)", w)
            if m:                                  # 3M · 60M 처럼 숫자가 있는 것만
                b_tot += 1
                # 1M은 "매월"의 인코딩인 경우가 있다 — 약관에 숫자 1이 나올 이유가 없다.
                # 센티넬과 같은 성격이므로 해당 낱말이 근거에 있으면 접지된 것으로 본다.
                word_coded = (w == "1M" and any(
                    x in _normalize(ev) for x in ("매월", "월단위", "월별")))
                if m.group(1) in ev_nums or word_coded:
                    b_hit += 1
                else:
                    b_fails.append((r["rule_id"], "window", w))

        c = r.get("cap_pp", "").strip()
        if c:
            b_tot += 1
            try:
                ok = grounded(float(c), ev)
            except ValueError:
                ok = False
            if ok:
                b_hit += 1
            else:
                b_fails.append((r["rule_id"], "cap_pp", c))

        for k in ("attribution_rule", "inclusion_set", "exclusion_set"):
            v = r.get(k, "").strip()
            if v:
                b_tot += 1
                if _span_grounded(v, ev):
                    b_hit += 1
                else:
                    b_fails.append((r["rule_id"], k, v[:34]))

    if b_tot:
        print(f"[B] 기간·상한·귀속·집합 접지: {b_hit}/{b_tot} ({b_hit / b_tot:.0%})")
    if b_fails:
        print(f"\n[B] 남은 누락 {len(b_fails)}건 — 근거 원문을 번들에 추가해야 합니다")
        for rid, k, v in b_fails:
            print(f"  ★ {rid:32s} {k:18s} {v}")

    all_tot, all_hit = tot + b_tot, hit + b_hit
    if all_tot:
        print(f"\n전체 활성 필드 접지: {all_hit}/{all_tot} ({all_hit / all_tot:.0%})")

    if fails:
        print("\n[A] 남은 누락:")
        for rid, k, v in fails:
            print(f"  {rid} {k}={v:g}")
        return 1
    print("전 필드 접지 완료 — 역할 C 수치 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
