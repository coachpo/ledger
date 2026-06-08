#!/bin/sh
set -eu

PORT="${PORT:-8080}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
RUN_SCHEDULER="${RUN_SCHEDULER:-true}"
SIGNALDECK_RUNTIME_MODE="${SIGNALDECK_RUNTIME_MODE:-local}"
SIGNALDECK_ROOT_IMAGE_SCOPE="${SIGNALDECK_ROOT_IMAGE_SCOPE:-local-demo-only}"

case "$SIGNALDECK_RUNTIME_MODE" in
  production|prod|staging|PRODUCTION|PROD|STAGING)
    echo "The root combined SignalDeck image is local/demo-only. Use backend/Dockerfile and frontend/Dockerfile images for production." >&2
    exit 1
    ;;
esac

echo "Starting SignalDeck root combined image in ${SIGNALDECK_ROOT_IMAGE_SCOPE} mode." >&2

export PORT BACKEND_PORT SIGNALDECK_RUNTIME_MODE SIGNALDECK_ROOT_IMAGE_SCOPE

mkdir -p /etc/supervisor/conf.d /run/nginx
rm -f /etc/supervisor/conf.d/*.conf

envsubst '${PORT} ${BACKEND_PORT}' \
    </etc/nginx/templates/default.conf.template \
    >/etc/nginx/conf.d/default.conf

cat >/app/run-backend.sh <<'EOF'
#!/bin/sh
set -eu
cd /app
BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_CMD="${BACKEND_CMD:-uvicorn app.main:app --host 127.0.0.1 --port ${BACKEND_PORT}}"
exec sh -c "$BACKEND_CMD"
EOF

cat >/app/run-scheduler.sh <<'EOF'
#!/bin/sh
set -eu
cd /app
SCHEDULER_CMD="${SCHEDULER_CMD:-python -m app.workers.run_scheduler}"
exec sh -c "$SCHEDULER_CMD"
EOF
chmod +x /app/run-backend.sh /app/run-scheduler.sh

cat >/etc/supervisor/conf.d/backend.conf <<'EOF'
[program:backend]
command=/app/run-backend.sh
directory=/app
autostart=true
autorestart=true
startsecs=5
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
stderr_logfile=/dev/fd/2
stderr_logfile_maxbytes=0
stopasgroup=true
killasgroup=true
EOF

cat >/etc/supervisor/conf.d/nginx.conf <<'EOF'
[program:nginx]
command=/usr/sbin/nginx -g "daemon off;"
autostart=true
autorestart=true
priority=20
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
stderr_logfile=/dev/fd/2
stderr_logfile_maxbytes=0
stopasgroup=true
killasgroup=true
EOF

case "$RUN_SCHEDULER" in
  true|TRUE|True|1|yes|YES)
    cat >/etc/supervisor/conf.d/scheduler.conf <<'EOF'
[program:scheduler]
command=/app/run-scheduler.sh
directory=/app
autostart=true
autorestart=true
startsecs=5
priority=10
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
stderr_logfile=/dev/fd/2
stderr_logfile_maxbytes=0
stopasgroup=true
killasgroup=true
EOF
    ;;
  false|FALSE|False|0|no|NO)
    ;;
  *)
    echo "RUN_SCHEDULER must be true or false" >&2
    exit 1
    ;;
esac

nginx -t
exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
