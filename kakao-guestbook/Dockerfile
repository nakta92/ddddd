# 카카오 방명록 - FastAPI + SQLite
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # DB와 업로드 파일은 /data 볼륨에 저장 (컨테이너를 지워도 유지)
    DATABASE_URL=sqlite:////data/guestbook.db \
    UPLOAD_DIR=/data/uploads

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# root가 아닌 사용자로 실행. /data는 이 사용자 소유로 만들어 두면 named volume이 소유권을 이어받습니다.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data/uploads \
    && chown -R appuser:appuser /data
USER appuser

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# 실시간(SSE) pub/sub이 메모리 기반이라 워커는 1개로 실행합니다.
# --proxy-headers: Nginx/ALB 뒤에서 실제 클라이언트 IP·https 인식 (신뢰할 프록시는 FORWARDED_ALLOW_IPS로 지정)
# --timeout-graceful-shutdown: 열린 SSE 연결 때문에 종료가 지연되지 않도록 제한
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--timeout-graceful-shutdown", "5"]
