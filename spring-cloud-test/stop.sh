#!/usr/bin/env bash
# run.sh 로 띄운 서비스 종료
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$ROOT_DIR/.pids"

if [ ! -d "$PID_DIR" ]; then
  echo "[stop] 실행 중인 서비스가 없습니다."
  exit 0
fi

for service in api-gateway board-service auth-service eureka-server; do
  pid_file="$PID_DIR/$service.pid"
  [ -f "$pid_file" ] || continue

  pid="$(cat "$pid_file")"
  if kill "$pid" 2>/dev/null; then
    echo "[stop] $service 종료 (pid $pid)"
  fi
  rm -f "$pid_file"
done
