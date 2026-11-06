#!/usr/bin/env python3
"""Tiny Govee controller: LAN (UDP) for devices that support it, Cloud API for the rest.

Usage:
  govee.py discover            # find LAN-enabled devices on your network (IP, sku)
  govee.py devices             # list cloud devices (needs GOVEE_API_KEY) -> device IDs
  govee.py run <action>        # run an action defined in config.json
  govee.py run <action> --dry  # print what would be sent
  govee.py schedule            # show today's computed run times (incl. sunset)
  govee.py daemon              # long-running scheduler (what launchd keeps alive)
Stdlib only; Python 3.8+.
"""
import datetime as dt, json, math, os, socket, struct, sys, time, urllib.request, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.environ.get("GOVEE_CONFIG", os.path.join(HERE, "config.json"))
CLOUD = "https://openapi.api.govee.com/router/api/v1"


def _load_env():
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p):
            k, _, v = line.strip().partition("=")
            if k and not k.startswith("#"):
                os.environ.setdefault(k, v.strip().strip('"'))


_load_env()


# ---------- LAN (UDP) ----------
def lan_discover(wait=3.0):
    """Multicast scan; devices reply on UDP 4002."""
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx.bind(("", 4002))
    rx.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                  struct.pack("4sl", socket.inet_aton("239.255.255.250"), socket.INADDR_ANY))
    rx.settimeout(0.5)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx.sendto(json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}).encode(),
              ("239.255.255.250", 4001))
    found, end = {}, time.time() + wait
    while time.time() < end:
        try:
            data, _ = rx.recvfrom(4096)
            d = json.loads(data)["msg"]["data"]
            found[d["ip"]] = d
        except (socket.timeout, KeyError, ValueError):
            pass
    return list(found.values())


def lan_send(ip, cmd, data):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(json.dumps({"msg": {"cmd": cmd, "data": data}}).encode(), (ip, 4003))


def lan_apply(dev, step, dry):
    ip = dev["ip"]
    if "power" in step:
        send(dry, "LAN", ip, "turn", {"value": 1 if step["power"] else 0}, lambda: lan_send(ip, "turn", {"value": 1 if step["power"] else 0}))
    if "brightness" in step:
        d = {"value": int(step["brightness"])}
        send(dry, "LAN", ip, "brightness", d, lambda: lan_send(ip, "brightness", d))
    if "color" in step or "kelvin" in step:
        r, g, b = step.get("color", [0, 0, 0])
        d = {"color": {"r": r, "g": g, "b": b}, "colorTemInKelvin": step.get("kelvin", 0)}
        send(dry, "LAN", ip, "colorwc", d, lambda: lan_send(ip, "colorwc", d))


# ---------- Cloud ----------
def api_key():
    k = os.environ.get("GOVEE_API_KEY")
    if not k:
        sys.exit("Set GOVEE_API_KEY (see README).")
    return k


def cloud(method, path, body=None):
    req = urllib.request.Request(CLOUD + path, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Govee-API-Key": api_key(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def cloud_ctl(sku, device, ctype, instance, value):
    return cloud("POST", "/device/control", {"requestId": str(uuid.uuid4()), "payload": {
        "sku": sku, "device": device,
        "capability": {"type": "devices.capabilities." + ctype, "instance": instance, "value": value}}})


def cloud_apply(dev, step, dry):
    sku, did = dev["sku"], dev["device_id"]
    ops = []
    if "power" in step:
        ops.append(("on_off", "powerSwitch", 1 if step["power"] else 0))
    if "brightness" in step:
        ops.append(("range", "brightness", int(step["brightness"])))
    if "color" in step:
        r, g, b = step["color"]
        ops.append(("color_setting", "colorRgb", (r << 16) | (g << 8) | b))
    if "kelvin" in step:
        ops.append(("color_setting", "colorTemperatureK", int(step["kelvin"])))
    for ctype, inst, val in ops:
        send(dry, "CLOUD", sku, inst, val, lambda: cloud_ctl(sku, did, ctype, inst, val))
        time.sleep(0.4)  # be kind to the rate limit


def send(dry, kind, target, what, val, fn):
    print(f"[{kind}] {target} {what}={val}" + (" (dry)" if dry else ""))
    if not dry:
        fn()


# ---------- Sun times (NOAA "sunrise equation", stdlib only) ----------
def sun_event(day, lat, lon, kind):
    """Local-time datetime of 'sunrise' or 'sunset' on `day` (a date), or None (polar day/night)."""
    n = day.toordinal() + 1721424.5 + 0.5 - 2451545.0
    jstar = n - lon / 360.0
    m = math.radians((357.5291 + 0.98560028 * jstar) % 360)
    c = 1.9148 * math.sin(m) + 0.02 * math.sin(2 * m) + 0.0003 * math.sin(3 * m)
    lam = math.radians((math.degrees(m) + c + 180 + 102.9372) % 360)
    jt = 2451545.0 + jstar + 0.0053 * math.sin(m) - 0.0069 * math.sin(2 * lam)
    sin_d = math.sin(lam) * math.sin(math.radians(23.4397))
    cos_d = math.cos(math.asin(sin_d))
    cos_w = (math.sin(math.radians(-0.833)) - math.sin(math.radians(lat)) * sin_d) / (math.cos(math.radians(lat)) * cos_d)
    if not -1 <= cos_w <= 1:
        return None
    w = math.degrees(math.acos(cos_w))
    j = jt + (w if kind == "sunset" else -w) / 360.0
    utc = dt.datetime(2000, 1, 1, 12, tzinfo=dt.timezone.utc) + dt.timedelta(days=j - 2451545.0)
    return utc.astimezone()  # system local timezone


def entry_time(entry, day, cfg):
    """When does this schedule entry fire on `day`? (local aware datetime, or None)"""
    if "sun" in entry:
        loc = cfg["location"]
        t = sun_event(day, loc["lat"], loc["lon"], entry["sun"])
        return t + dt.timedelta(minutes=entry.get("offset_min", 0)) if t else None
    h, m = map(int, entry["time"].split(":"))
    return dt.datetime.combine(day, dt.time(h, m)).astimezone()


def run_action(cfg, name, dry=False):
    for step in cfg["actions"][name]:
        dev = cfg["devices"][step["device"]]
        (lan_apply if dev["mode"] == "lan" else cloud_apply)(dev, step, dry)


def show_schedule(cfg):
    today = dt.date.today()
    for e in sorted(cfg["schedule"], key=lambda e: entry_time(e, today, cfg) or dt.datetime.max.astimezone()):
        t = entry_time(e, today, cfg)
        how = f"{e['sun']}{e.get('offset_min', 0):+d}m" if "sun" in e else e["time"]
        print(f"{t.strftime('%H:%M') if t else '--:--'}  {e['action']:<16} ({how})")


def daemon(catchup_min=20):
    """Check every 20s; fire due entries once per day. Runs missed entries if the Mac was asleep
    for less than `catchup_min` minutes past the scheduled time."""
    fired, last_day = set(), None
    while True:
        cfg = json.load(open(CONFIG))  # re-read each loop: edit config without restarting
        now = dt.datetime.now().astimezone()
        today = now.date()
        if today != last_day:
            fired, last_day = set(), today
            print(f"--- {today} ---", flush=True)
            show_schedule(cfg)
            sys.stdout.flush()
        for i, e in enumerate(cfg["schedule"]):
            t = entry_time(e, today, cfg)
            key = (i, e["action"])
            if t and key not in fired and t <= now:
                fired.add(key)
                if now - t <= dt.timedelta(minutes=catchup_min):
                    print(f"{now:%H:%M:%S} firing {e['action']}", flush=True)
                    try:
                        run_action(cfg, e["action"])
                    except Exception as ex:  # keep the daemon alive
                        print("  ERROR:", ex, flush=True)
        time.sleep(20)


# ---------- main ----------
def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "discover":
        print(json.dumps(lan_discover(), indent=2))
    elif a[0] == "devices":
        for d in cloud("GET", "/user/devices").get("data", []):
            print(d["sku"], d["device"], d.get("deviceName", ""))
    elif a[0] == "run" and len(a) > 1:
        run_action(json.load(open(CONFIG)), a[1], "--dry" in a)
    elif a[0] == "schedule":
        show_schedule(json.load(open(CONFIG)))
    elif a[0] == "daemon":
        daemon()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
