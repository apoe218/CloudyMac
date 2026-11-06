#!/usr/bin/env python3
"""Install/remove ONE launchd agent that keeps `govee.py daemon` running (starts at login, restarts on crash).
Usage: install_schedule.py install | uninstall | status
"""
import os, plistlib, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LABEL = "com.cloudymac.govee"
PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
DOMAIN = f"gui/{os.getuid()}"
LOG = os.path.expanduser("~/Library/Logs/govee.log")


def launchctl(*args):
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def main():
    cmd = (sys.argv[1:] or ["status"])[0]
    launchctl("bootout", f"{DOMAIN}/{LABEL}")  # ignore errors if not loaded
    if cmd == "install":
        os.makedirs(os.path.dirname(PLIST), exist_ok=True)
        with open(PLIST, "wb") as f:
            plistlib.dump({
                "Label": LABEL,
                "ProgramArguments": [sys.executable or "/usr/bin/python3", "-u", os.path.join(HERE, "govee.py"), "daemon"],
                "WorkingDirectory": HERE,
                "RunAtLoad": True, "KeepAlive": True,
                "StandardOutPath": LOG, "StandardErrorPath": LOG,
            }, f)
        r = launchctl("bootstrap", DOMAIN, PLIST)
        print("installed and started" if r.returncode == 0 else f"bootstrap failed: {r.stderr}")
        print("log:", LOG)
    elif cmd == "uninstall":
        if os.path.exists(PLIST):
            os.remove(PLIST)
        print("uninstalled")
    else:
        r = launchctl("print", f"{DOMAIN}/{LABEL}")
        print("running" if r.returncode == 0 else "not installed")


main()
