# DEV25 / FINAL_UNSEEN 채점 필드 정의 (Gold 없음)

이 파일은 **채점 기준 정의만** 담는다. Gold 정답은 여기 없고, 앞으로도 이 폴더에 넣지
않는다 (`DO_NOT_ADD_GOLD.txt` 참조). 채점은 별도 담당자가 Gold를 가지고 수행한다.

## 최종 채점 지표 (PROJECT_CURRENT_STATE.md / 이동학_최종_실행지시 §6)

| 지표 | 정의 | 계산 방식(제안) |
|---|---|---|
| Field/Exact Rule Match | 핵심 필드가 Gold와 얼마나 정확히 일치하는지 | 16필드 중 Gold와 값이 일치하는 필드 비율 |
| Exception Recall | 예외·제외조건을 놓치지 않는지 | Gold에 exception이 있는 샘플 중 `exception`이 채워진 비율 |
| Attribution Recall | 귀속조건(결제계좌/명의 등)을 잡는지 | Gold에 attribution_rule이 있는 샘플 중 채워진 비율 |
| Complex Structure Accuracy | OR·tier·window·grace·recalc 등 복합구조 정확도 | 해당 필드가 있는 샘플만 따로 집계 |
| Evidence Grounding | 출력 수치가 원문 근거에 실제로 연결되는지 | `ai_rule.ungrounded_numbers()` 결과가 빈 배열인 비율 |
| Dangerous Error Rate | 원문에 없는 수치/조건을 지어내고 통과시키는 비율 | accepted=Y인데 실제로는 ungrounded_numbers가 비지 않은 경우 (Gate 무력화율) |
| Executable Rule Rate | 엔진이 바로 계산 가능한 구조로 나온 비율 | `rule_store`가 요구하는 최소 필드(threshold/effect 또는 tiers)가 채워진 비율 |

## 기관별로 쪼개서 봐야 하는 이유

2026-08-25 작업보고에 기록된 대로 BLIND25 25건 중 IBK 8건(그중 5건이 사실상 같은
상품의 변형)·카카오뱅크 6건이 56%를 차지한다. 총점만 보면 이 두 기관 형식이 결과를
크게 좌우하므로, 채점자는 기관별/archetype별로 나눠서 봐야 한다.

## 이 세션에서 한 것 — 채점이 아니라 파이프라인 검증

`dev25_runner.py`를 mock 모드로 실행해 175행이 기계적으로 만들어지는지, 스키마가
깨지지 않는지, Gate가 실제로 동작하는지(조작된 값 차단)만 확인했다. **이건 Gold 채점이
아니다** — 실제 채점은 별도 담당자가 Gold를 가지고 위 지표대로 진행해야 한다.
