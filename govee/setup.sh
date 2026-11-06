#!/bin/bash
# One-shot Mac setup. Run from the govee/ folder:  bash setup.sh
set -e
cd "$(dirname "$0")"
PY=$(command -v python3 || true)
[ -z "$PY" ] && { echo "python3 missing. Run: xcode-select --install"; exit 1; }

echo "== 1/5 Cloud API key (for the H6002 lamps) =="
if [ ! -f .env ]; then
  echo "Get one at https://developer.govee.com/ (emailed to you)."
  read -r -s -p "Paste Govee API key (hidden): " KEY; echo
  printf 'GOVEE_API_KEY=%s\n' "$KEY" > .env; chmod 600 .env
fi

echo "== 2/5 Find Christmas Lights on your network =="
echo "(Enable LAN Control for the lights in the Govee Home app first.)"
"$PY" govee.py discover || true
read -r -p "Christmas Lights IP (from above): " LIGHT_IP

echo "== 3/5 Cloud devices =="
"$PY" govee.py devices || true
read -r -p "Living Room Lamp device_id: " LIVING
read -r -p "Bedroom Lamp device_id: " BEDROOM
read -r -p "Your latitude  (e.g. 29.7604): " LAT
read -r -p "Your longitude (e.g. -95.3698): " LON

echo "== 4/5 Writing config.json =="
[ -f config.json ] && cp config.json config.json.bak
LIGHT_IP="$LIGHT_IP" LIVING="$LIVING" BEDROOM="$BEDROOM" LAT="$LAT" LON="$LON" "$PY" - <<'PYEOF'
import json, os
c = json.load(open("config.example.json"))
e = os.environ
c["location"] = {"lat": float(e["LAT"]), "lon": float(e["LON"])}
c["devices"]["christmas"]["ip"] = e["LIGHT_IP"]
c["devices"]["living"]["device_id"] = e["LIVING"]
c["devices"]["bedroom"]["device_id"] = e["BEDROOM"]
json.dump(c, open("config.json", "w"), indent=2)
PYEOF
"$PY" govee.py schedule

echo "== 5/5 Test + install =="
read -r -p "Blink test: turn Christmas Lights on now? [y/N] " Y
[ "$Y" = "y" ] && "$PY" govee.py run lights_on
"$PY" install_schedule.py install
echo "Done. Logs: ~/Library/Logs/govee.log   (tail -f it to watch)"
echo "Also: System Settings > Battery/Energy > prevent automatic sleeping."
