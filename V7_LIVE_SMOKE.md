# V7_LIVE_SMOKE.md — Render 실제 배포 스모크 체크리스트

이 세션(클라우드 샌드박스)은 `https://butterfin.onrender.com`에 직접 접속할 수
없고, 실제 Chrome/모바일 브라우저도 없다. 그래서 이 문서는 "이미 확인한 것"과
"동학님이 배포 후 직접 눈으로 확인해야 하는 것"을 정직하게 나눈다 — 확인 안 한
걸 확인했다고 쓰지 않는다.

## 이 세션에서 실제로 검증한 것 (로컬 Flask 서버 기준)

- `GET /` → 200, `mvp/static/index.html` 정상 응답(44,589바이트)
- `GET /api/health` → 200, `rules_loaded=8`, `rules_all_fresh=True`,
  `ar_mode=DEMO`
- `POST /api/evaluate` — 13개 케이스(§A) + 3개 Golden Demo(§B) 전부 로컬에서
  실제 요청/응답으로 검증(`V7_TEST_REPORT.md` 참조)
- 파이썬 구문 오류 없음(`python3 -m py_compile mvp/*.py` 통과 — 아래 참조)

## 배포 후 동학님이 직접 확인해야 하는 것

1. **git push 후 실제 반영 확인**: Render는 실제 `git push`가 일어난 뒤에만
   재배포한다. push 직후 Render 대시보드에서 배포가 끝났는지(보통 1~3분) 확인하고,
   `https://butterfin.onrender.com`을 **하드 리프레시(Cmd+Shift+R / Ctrl+Shift+R)**
   해서 브라우저 캐시된 옛 화면이 아닌지 확인.
2. **3개 Golden Demo를 실제 화면에서 클릭으로 재현**:
   - KB국민은행/대출 금리감면, 5만원 → HOLD 배지 + "10. Action Reversal: 예"
     확인, 2만원으로 바꿔 PASS로 전환되는지.
   - 주택금융공사/내집마련 디딤돌대출, "예외 조건 체크" 켜고 PASS 확인.
   - PRODUCT_TERMINATION을 기관/상품 미지정으로 보내면 REVIEW + 후보 목록
     화면(이번에 추가한 "영향받을 수 있는 보유계약 후보" 카드)이 실제로 뜨는지.
3. **디딤돌대출 REVIEW 화면**: 예외 체크 끄고 가입기간/납입회차 정보 없이 해지
   시나리오를 넣었을 때, 화면에 `condition.review_note` 문구("가입기간/납입회차
   정보가 없어...")가 실제로 보이는지.
4. **이산형 3유형(해지/결제계좌 변경/급여계좌 변경) 화면에서 "10. Action
   Reversal" 섹션이 아예 안 뜨고 "10. 조건 유지/위반" 섹션이 대신 뜨는지**,
   CARD_SPEND_SHIFT에서는 반대로 "10. Action Reversal"이 정상적으로 뜨는지.
5. **퍼센트 입력창**: "새로 가입하려는 상품의 금리(%)" 입력창이 화면에 그대로
   있는지, 값을 넣었을 때 예전처럼 "유리/불리" 배지가 뜨지 않고 그냥 입력값 +
   설명 문구만 뜨는지.
6. **모바일 브라우저**에서 레이아웃이 깨지지 않는지(이 세션은 모바일 렌더링을
   확인할 수 없음).
7. **실제 OpenAI 키가 걸린 프로덕션 환경**에서 `/api/interpret`이 정상 동작하는지
   (이 세션은 키가 없어 mock/에러-주입으로만 검증함).

## 로컬 구문/임포트 확인 (참고용, 실행 로그)

```
$ python3 -m py_compile mvp/app.py mvp/rule_store.py mvp/engine.py mvp/action_interpreter.py
(에러 없음 — 아래 "실행 로그" 절 참조)
```

이 체크리스트의 1~7번은 "테스트로 자동화 못 하는, 실제 배포 환경/실제 브라우저가
있어야만 확인 가능한 항목"이다. 이걸 자동으로 통과했다고 주장하지 않는다.
