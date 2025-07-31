#!/bin/sh
set -e

if [ -z "$SLACK_WEBHOOK_URL" ]; then
  echo "Warning: SLACK_WEBHOOK_URL is not set. Slack notifications disabled." >&2
  cat <<EOCONFIG > /tmp/alertmanager.yml
route:
  receiver: dummy
receivers:
  - name: dummy
EOCONFIG
else
  /usr/local/bin/envsubst < /etc/alertmanager/alertmanager.yml > /tmp/alertmanager.yml
fi

exec /bin/alertmanager --config.file=/tmp/alertmanager.yml "$@"
