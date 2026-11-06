# Govee automation (always-on Mac)

- **Christmas Lights (H70C2)** -> LAN control (local UDP, no cloud).
- **Lamps (H6002 x2)** -> Govee Cloud API (they have no LAN Control).

## Setup
1. Govee Home app -> Christmas Lights -> Settings -> enable **LAN Control**.
2. Give the lights a DHCP reservation in your router so the IP never changes.
3. `python3 govee.py discover` -> copy the light's `ip`.
4. Get a cloud API key at developer.govee.com (emailed to you), then:
   `export GOVEE_API_KEY=...` and run `python3 govee.py devices` -> copy each lamp's `device_id`.
5. `cp config.example.json config.json` and fill in IPs/IDs, actions, times.
   (`config.json` is git-ignored; never commit your API key.)
6. Test: `python3 govee.py run evening --dry`, then without `--dry`.
7. Schedule: `GOVEE_API_KEY=... python3 install_schedule.py install`
   Remove: `python3 install_schedule.py uninstall`. Logs: `/tmp/govee.log`.

Re-run `install_schedule.py install` after editing the schedule in config.json.
The Mac must be awake at run times (System Settings -> Battery/Energy -> prevent sleep).
