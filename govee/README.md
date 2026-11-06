# Govee automation (always-on Mac)

- **Christmas Lights (H70C2)** -> LAN control (local UDP, no cloud), scheduled by **sunset**.
- **Lamps (H6002 x2)** -> Govee Cloud API (no LAN Control on these).

## Quick start (Mac)
```bash
git clone https://github.com/apoe218/CloudyMac.git && cd CloudyMac && git checkout claude/fancy-wares-village
cd govee && bash setup.sh
```
Before running: in the Govee Home app enable **LAN Control** on the Christmas Lights, and give them a
DHCP reservation in your router. `setup.sh` asks for your API key (saved to git-ignored `.env`, chmod 600),
discovers the lights, writes `config.json`, and installs a launchd agent that keeps `govee.py daemon` running.

## Schedule entries (config.json)
```json
{"action": "lights_on", "sun": "sunset",  "offset_min": -10}   // 10 min before sunset
{"action": "night_off", "sun": "sunrise", "offset_min": 0}
{"action": "bedtime",   "time": "22:00"}                       // fixed local time
```
Sun times are computed on the Mac for your `location` and system timezone (verified against known values).
Edits to `config.json` are picked up automatically (no restart). If the Mac was asleep, an entry missed by
less than 20 minutes still fires on wake.

## Commands
```
python3 govee.py schedule         # today's times, incl. sunset
python3 govee.py run lights_on    # fire an action now (add --dry to preview)
python3 install_schedule.py status|install|uninstall
tail -f ~/Library/Logs/govee.log
```
Keep the Mac from sleeping (System Settings -> Battery/Energy). Never commit `.env` or `config.json`.
