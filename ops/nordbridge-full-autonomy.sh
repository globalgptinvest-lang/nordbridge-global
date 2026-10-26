#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

# Safe NordBridge autonomous controller.
# It never sends mail/WhatsApp, changes prices/payments, or bypasses CAPTCHA.
STATE_DIR=${NORDBRIDGE_STATE_DIR:-/var/lib/nordbridge-autonomy}
LOG_DIR=${NORDBRIDGE_LOG_DIR:-/var/log/nordbridge-autonomy}
SCRIPT_DST=/usr/local/sbin/nordbridge-autonomy.sh
SERVICE=/etc/systemd/system/nordbridge-autonomy.service
TIMER=/etc/systemd/system/nordbridge-autonomy.timer
LOCK=/run/nordbridge-autonomy.lock
REPORT="$STATE_DIR/last-run.json"
MODE=health
INSTALL_TIMER=1

for arg in "$@"; do
  case "$arg" in
    --full) MODE=full ;;
    --health-only) MODE=health ;;
    --no-timer) INSTALL_TIMER=0 ;;
    --help) echo 'Usage: sudo bash nordbridge-full-autonomy.sh [--full|--health-only] [--no-timer]'; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo 'BLOCKED: run as root (sudo).' >&2; exit 3; }
mkdir -p -m 0700 "$STATE_DIR" "$LOG_DIR"
exec 9>"$LOCK"
flock -n 9 || { echo 'SKIPPED: another NordBridge check is running.'; exit 0; }

RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
LOG="$LOG_DIR/run-$RUN_ID.log"
exec > >(tee -a "$LOG") 2>&1

status=WORKING
docker_status='NOT VERIFIED'
monitor_status='NOT VERIFIED'
website_status='NOT VERIFIED'
crm_status='NOT VERIFIED'
backup_status='NOT RUN'
restore_status='NOT RUN'
timer_status='NOT VERIFIED'
email_status='BLOCKED_OWNER_AUTH_REQUIRED'
whatsapp_status='BLOCKED_OWNER_AUTH_REQUIRED'
offsite_status='BLOCKED_NOT_CONFIGURED'
captcha_status='NOT_VERIFIED_MANUAL_TEST_REQUIRED'
error_count=0
fail() { error_count=$((error_count + 1)); status=FAILED; }

echo "NORDBRIDGE_AUTONOMY_START=$RUN_ID MODE=$MODE"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker_status=WORKING
  running=$(docker ps -q | wc -l | tr -d ' ')
  echo "DOCKER=WORKING RUNNING_CONTAINERS=$running"
else
  docker_status=FAILED; fail; echo 'DOCKER=FAILED'
fi

required_containers=(
  nordbridge-crm-api-1 nordbridge-crm-db-1 nordbridge-director-director-1
  nordbridge-office-caddy-1 nordbridge-office-core-1 nordbridge-office-n8n-1
  nordbridge-office-worker-1 nordbridge-office-postgres-1 nordbridge-office-redis-1
  nordbridge-office-qdrant-1 nordbridge-office-ollama-1
)
missing=0
for container in "${required_containers[@]}"; do
  state=$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)
  if [[ "$state" != true && "$state" != "" ]]; then
    echo "CONTAINER_START_ATTEMPT=$container"
    docker start "$container" >/dev/null 2>&1 || true
    state=$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)
  fi
  if [[ "$state" != true ]]; then
    echo "CONTAINER_NOT_RUNNING=$container"
    missing=$((missing + 1))
  fi
done
if [[ $missing -eq 0 && "$docker_status" == WORKING ]]; then echo 'CONTAINERS=WORKING'; else fail; fi

if [[ -f /opt/nordbridge-director/monitor.py ]]; then
  if monitor_json=$(python3 /opt/nordbridge-director/monitor.py 2>/dev/null); then
    monitor_status=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print("WORKING" if d.get("healthy") is True else "FAILED")' <<<"$monitor_json" 2>/dev/null || echo FAILED)
    [[ "$monitor_status" == WORKING ]] || fail
    printf '%s\n' "$monitor_json" > "$STATE_DIR/monitor-$RUN_ID.json"
    chmod 0600 "$STATE_DIR/monitor-$RUN_ID.json"
  else
    monitor_status=FAILED; fail
  fi
else
  monitor_status=BLOCKED_MISSING_MONITOR; fail
fi
echo "DIRECTOR_MONITOR=$monitor_status"

probe_json() {
  local url=$1 out=$2 code
  code=$(curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --connect-timeout 5 --max-time 12 -o "$out" -w '%{http_code}' "$url" 2>/dev/null || true)
  [[ "$code" == 200 ]] || return 1
  python3 - "$out" <<'PY'
import json,sys
with open(sys.argv[1],encoding='utf-8') as f: data=json.load(f)
if sys.argv[1].endswith('website.json'):
    raise SystemExit(0 if data.get('ready') is True and not data.get('testing',False) else 1)
raise SystemExit(0 if data.get('ready') is True else 1)
PY
}
if probe_json https://www.nordbridge-global.com/api/intake-status "$TMP/website.json"; then website_status=WORKING; else website_status=FAILED; fail; fi
if probe_json https://crm.57.129.182.200.sslip.io/health "$TMP/crm.json"; then crm_status=WORKING; else crm_status=FAILED; fail; fi
echo "WEBSITE_INTAKE=$website_status CRM_HEALTH=$crm_status"

if [[ "$MODE" == full ]]; then
  if systemctl start nordbridge-recovery-backup.service >/dev/null 2>&1; then
    backup_status=WORKING
    latest=$(find /var/backups/nordbridge-maintenance -mindepth 2 -maxdepth 2 -name result.json -type f -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n1 | cut -d' ' -f2- || true)
    if [[ -n "$latest" ]] && python3 - "$latest" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
pg=d.get('postgres',[])
raise SystemExit(0 if len(pg)==2 and all(x.get('restore',{}).get('status')=='WORKING' for x in pg) else 1)
PY
    then restore_status=WORKING; else restore_status=FAILED; fail; fi
  else
    backup_status=FAILED; restore_status=FAILED; fail
  fi
fi
echo "BACKUP=$backup_status RESTORE=$restore_status"

existing_timer=0
for candidate in /etc/systemd/system/nordbridge-*.timer /lib/systemd/system/nordbridge-*.timer; do
  [[ -e "$candidate" ]] || continue
  [[ "$candidate" == "$TIMER" ]] && continue
  if grep -Eqi 'monitor|health|director' "$candidate" 2>/dev/null; then existing_timer=1; fi
done
if [[ $INSTALL_TIMER -eq 1 && $existing_timer -eq 0 ]]; then
  if [[ -f "$0" && "$0" != /dev/* ]]; then install -o root -g root -m 0750 "$0" "$SCRIPT_DST"; fi
  cat > "$SERVICE" <<'UNIT'
[Unit]
Description=NordBridge autonomous health controller
After=docker.service network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/nordbridge-autonomy.sh --health-only --no-timer
UNIT
  cat > "$TIMER" <<'UNIT'
[Unit]
Description=NordBridge autonomous health controller timer
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true
Unit=nordbridge-autonomy.service
[Install]
WantedBy=timers.target
UNIT
  systemctl daemon-reload
  if systemctl enable --now nordbridge-autonomy.timer >/dev/null 2>&1; then timer_status=WORKING; else timer_status=FAILED; fail; fi
elif [[ $existing_timer -eq 1 ]]; then
  timer_status=WORKING_EXISTING_TIMER
else
  timer_status=NOT_INSTALLED_OPTIONAL
fi
echo "AUTONOMY_TIMER=$timer_status"

if env | grep -Eq '^(GMAIL_|IMAP_|SMTP_)'; then email_status=PRESENT_NOT_VERIFIED; fi
if env | grep -Eq '^(WHATSAPP_|META_)'; then whatsapp_status=PRESENT_NOT_VERIFIED; fi
if [[ ${NORDBRIDGE_OFFSITE_BACKUP_ENABLED:-0} == 1 ]]; then offsite_status=CONFIGURED_NOT_VERIFIED; fi

export MODE FINAL_STATUS="$status" DOCKER_STATUS="$docker_status" MONITOR_STATUS="$monitor_status"
export WEBSITE_STATUS="$website_status" CRM_STATUS="$crm_status" BACKUP_STATUS="$backup_status"
export RESTORE_STATUS="$restore_status" TIMER_STATUS="$timer_status" EMAIL_STATUS="$email_status"
export WHATSAPP_STATUS="$whatsapp_status" OFFSITE_STATUS="$offsite_status" CAPTCHA_STATUS="$captcha_status"
export ERROR_COUNT="$error_count"
python3 - "$REPORT" <<'PY'
import datetime,json,os,sys
d={'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'mode':os.environ['MODE'],'status':os.environ['FINAL_STATUS'],'docker':os.environ['DOCKER_STATUS'],'monitor':os.environ['MONITOR_STATUS'],'website_intake':os.environ['WEBSITE_STATUS'],'crm_health':os.environ['CRM_STATUS'],'backup':os.environ['BACKUP_STATUS'],'restore':os.environ['RESTORE_STATUS'],'timer':os.environ['TIMER_STATUS'],'email':os.environ['EMAIL_STATUS'],'whatsapp':os.environ['WHATSAPP_STATUS'],'offsite_backup':os.environ['OFFSITE_STATUS'],'production_captcha':os.environ['CAPTCHA_STATUS'],'errors':int(os.environ['ERROR_COUNT'])}
with open(sys.argv[1],'w',encoding='utf-8') as f: json.dump(d,f,ensure_ascii=False,indent=2); f.write('\n')
os.chmod(sys.argv[1],0o600)
PY
echo "NORDBRIDGE_AUTONOMY_END=$RUN_ID STATUS=$status ERRORS=$error_count REPORT=$REPORT"
[[ "$status" != FAILED ]]

