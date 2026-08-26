FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mvp/ ./mvp/
COPY ablation/ ./ablation/

WORKDIR /app/mvp

# 빌드 시점 자가진단 — 여기서 실패하면 이미지가 만들어지지 않는다.
# (런타임에 발견하면 늦으므로 일부러 빌드 단계에서 잡는다.)
RUN python make_bundle.py

ENV AR_MODE=DEMO
ENV PORT=8000
EXPOSE 8000

# GEMINI_API_KEY는 여기 넣지 않는다 — 배포 플랫폼의 환경변수로만 설정한다.

CMD ["sh", "-c", "gunicorn -w 2 -b 0.0.0.0:${PORT} --timeout 30 app:app"]
