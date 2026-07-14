#!/bin/bash
START_MONO=$(systemctl show acars-collector -p ActiveEnterTimestampMonotonic --value 2>/dev/null)
if [ -n "$START_MONO" ]; then
    UPTIME=$(awk -v mono="$START_MONO" '{printf "%d", $1 - mono/1000000}' /proc/uptime)
    mkdir -p /var/lib/node-exporter
    cat > /var/lib/node-exporter/collector-uptime.prom <<EOF
# HELP collector_uptime_seconds Systemd service uptime in seconds
# TYPE collector_uptime_seconds gauge
collector_uptime_seconds $UPTIME
EOF
fi
