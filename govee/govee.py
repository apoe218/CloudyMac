#!/usr/bin/env python3
"""Tiny Govee controller: LAN (UDP) for devices that support it, Cloud API for the rest.

Usage:
  govee.py discover            # find LAN-enabled devices on your network (IP, sku)
  govee.py devices             # list cloud devices (needs GOVEE_API_KEY) -> device IDs
  govee.py run <action>        # run an action defined in config.json
  govee.py run <action> --dry  # print what would be sent
Stdlib only; Python 3.8+.
"""
import json, os, socket, struct, sys, time, urllib.request, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.environ.get("GOVEE_CONFIG", os.path.join(HERE, "config.json"))
CLOUD = "https://openapi.api.govee.com/router/api/v1"


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
        dry = "--dry" in a
        cfg = json.load(open(CONFIG))
        for step in cfg["actions"][a[1]]:
            dev = cfg["devices"][step["device"]]
            (lan_apply if dev["mode"] == "lan" else cloud_apply)(dev, step, dry)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
