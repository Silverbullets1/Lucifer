#!/bin/bash
# Tunnel watchdog: keeps a Cloudflare quick tunnel to :8000 alive,
# and writes the live URL to /tmp/lucifer_tunnel_url for frontend sync.
LOG=/tmp/lucifer_tunnel.log
URL_FILE=/tmp/lucifer_tunnel_url
while true; do
  # kill any stale cloudflared
  pkill -f "cloudflared tunnel --url http://localhost:8000" 2>/dev/null
  sleep 2
  # start fresh tunnel, capture output
  cloudflared tunnel --url http://localhost:8000 --logfile $LOG --loglevel info >/dev/null 2>&1 &
  CF_PID=$!
  # wait for URL to appear in log
  for i in $(seq 1 30); do
    URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$LOG" | tail -1)
    if [ -n "$URL" ]; then
      echo "$URL" > "$URL_FILE"
      echo "$(date) TUNNEL UP: $URL" >> "$LOG"
      break
    fi
    sleep 2
  done
  # monitor: if process dies or URL dead, loop restarts
  wait $CF_PID
  echo "$(date) TUNNEL DIED, restarting" >> "$LOG"
  sleep 5
done
