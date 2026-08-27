#!/usr/bin/env python3
"""
verify_deploy.py <url> — 배포된(또는 로컬) Action Reversal을 실제로 열어서 실측한다.

주의: 이 체크리스트는 이번 세션에서 새로 구성한 mvp/ 기준이다. 팀의 원래
verify_deploy.py(19/20개 항목, TC01 -23,200원/디딤돌 NPV 5,025,744원 등)는 원본 원장
CSV(action_reversal_rule_ledger_v3.csv, 37행)와 그 안의 실제 대출잔액 파라미터에
의존하는데 이번 세션에서는 그 파일에 접근할 수 없었다. 그래서 숫자를 베끼지 않고,
이 build가 실제로 계산한 값을 스스로 다시 측정해서 EXPECTED로 못박았다 — "몇 년 전
문서에 적힌 숫자"가 아니라 "이 스크립트를 처음 돌렸을 때 나온 값"이다.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error

EXPECTED_HEALTH = {
    "status": "ok",
    "ar_mode": "DEMO",
    "rules_loaded": 8,
}

EXPECTED_SCENARIOS = {
    "card_spend_shift": {"decision": "HOLD", "ttb_months": 2, "ttr_months": 2, "safe_limit_won": 20000},
    "termination_no_exception": {"decision": "HOLD"},
    "termination_with_exception": {"decision": "PASS"},
}


def check_health(base_url: str, report: dict) -> None:
    t0 = time.time()
    try:
        with urllib.request.urlopen(f"{base_url}/api/health", timeout=10) as r:
            body = json.loads(r.read().decode("utf-8"))
            status_code = r.status
    except urllib.error.URLError as e:
        report["checks"].append({"name": "health_reachable", "ok": False, "detail": str(e)})
        return
    latency_ms = int((time.time() - t0) * 1000)

    report["checks"].append({"name": "health_http_200", "ok": status_code == 200})
    report["checks"].append({"name": "health_status_ok", "ok": body.get("status") == "ok", "got": body.get("status")})
    report["checks"].append({"name": "ar_mode_demo", "ok": body.get("ar_mode") == "DEMO", "got": body.get("ar_mode")})
    report["checks"].append({"name": "rules_loaded_ge_expected",
                              "ok": (body.get("rules_loaded") or 0) >= EXPECTED_HEALTH["rules_loaded"],
                              "got": body.get("rules_loaded")})
    report["checks"].append({"name": "self_check_all_true",
                              "ok": all((body.get("self_check") or {}).values()),
                              "got": body.get("self_check")})
    report["checks"].append({"name": "response_under_3s", "ok": latency_ms < 3000, "got_ms": latency_ms})
    report["checks"].append({"name": "verified_at_present", "ok": bool(body.get("verified_at")),
                              "got": body.get("verified_at")})


def _post_json(url: str, payload: dict, timeout=40):
    # /api/interpret는 실제 Gemini 호출을 포함한다(내부 타임아웃 20s). 배포 환경(Render 등)의
    # 네트워크 경로가 로컬보다 느릴 수 있어 여유 있게 잡는다 — 너무 짧으면 서버는 멀쩡한데
    # 검증 스크립트만 타임아웃 나는 오탐이 생긴다.
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")), r.status


def check_scenarios(base_url: str, report: dict) -> None:
    # 1) 카드 사용액 이동
    try:
        interp, _ = _post_json(f"{base_url}/api/interpret",
                                {"text": "다음 달부터 카드사용 5만원을 다른 카드로 옮길 거야"})
        report["checks"].append({"name": "interpret_returns_ok",
                                  "ok": interp.get("delta", {}).get("status") == "OK",
                                  "got": interp.get("delta", {}).get("status")})
        ev, _ = _post_json(f"{base_url}/api/evaluate",
                            {"action_type": "CARD_SPEND_SHIFT", "amount_monthly": 50000})
        exp = EXPECTED_SCENARIOS["card_spend_shift"]
        for k, v in exp.items():
            report["checks"].append({"name": f"card_spend_shift.{k}", "ok": ev.get(k) == v,
                                      "got": ev.get(k), "expected": v})
    except (urllib.error.URLError, KeyError) as e:
        report["checks"].append({"name": "card_spend_shift_scenario", "ok": False, "detail": str(e)})

    # 2) 청약통장 해지 — 예외 미충족
    try:
        ev, _ = _post_json(f"{base_url}/api/evaluate",
                            {"action_type": "PRODUCT_TERMINATION", "institution": "주택금융공사"})
        exp = EXPECTED_SCENARIOS["termination_no_exception"]
        report["checks"].append({"name": "termination_no_exception.decision",
                                  "ok": ev.get("decision") == exp["decision"], "got": ev.get("decision")})
    except (urllib.error.URLError, KeyError) as e:
        report["checks"].append({"name": "termination_no_exception_scenario", "ok": False, "detail": str(e)})

    # 3) 청약통장 해지 — 예외(당첨) 충족
    try:
        ev, _ = _post_json(f"{base_url}/api/evaluate",
                            {"action_type": "PRODUCT_TERMINATION", "institution": "주택금융공사",
                             "exception_condition_met": True})
        exp = EXPECTED_SCENARIOS["termination_with_exception"]
        report["checks"].append({"name": "termination_with_exception.decision",
                                  "ok": ev.get("decision") == exp["decision"], "got": ev.get("decision")})
    except (urllib.error.URLError, KeyError) as e:
        report["checks"].append({"name": "termination_with_exception_scenario", "ok": False, "detail": str(e)})


def check_first_screen(base_url: str, report: dict) -> None:
    t0 = time.time()
    try:
        with urllib.request.urlopen(base_url, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")
            status_code = r.status
    except urllib.error.URLError as e:
        report["checks"].append({"name": "first_screen_reachable", "ok": False, "detail": str(e)})
        return
    latency_ms = int((time.time() - t0) * 1000)
    report["checks"].append({"name": "first_screen_http_200", "ok": status_code == 200})
    report["checks"].append({"name": "first_screen_under_3s", "ok": latency_ms < 3000, "got_ms": latency_ms})
    report["checks"].append({"name": "snapshot_label_present", "ok": "검증 스냅샷" in html or "snapshot" in html.lower()})


def main():
    parser = argparse.ArgumentParser(description="Action Reversal 배포 실측 검증")
    parser.add_argument("url", help="배포 URL (예: https://xxx.onrender.com) — 마지막 슬래시 없이")
    parser.add_argument("--out", default="DEPLOY_VERIFY_REPORT.json")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    report = {"target": base_url, "checked_at_note": "실행 시점 UTC 타임스탬프는 로그 참고", "checks": []}

    check_health(base_url, report)
    check_first_screen(base_url, report)
    check_scenarios(base_url, report)

    total = len(report["checks"])
    ok_count = sum(1 for c in report["checks"] for _ in [c] if c["ok"])
    report["summary"] = f"{ok_count}/{total}"
    report["all_ok"] = ok_count == total

    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report["all_ok"]:
        print(f"\n✅ {report['summary']} 전부 통과", file=sys.stderr)
    else:
        print(f"\n⚠️ {report['summary']} — 실패 항목 있음, 위 checks 확인", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
