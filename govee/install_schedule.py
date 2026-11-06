#!/usr/bin/env python3
"""Generate + load macOS launchd jobs from config.json's "schedule" (one per entry).
Usage: install_schedule.py install | uninstall
"""
import json, os, plistlib, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS = os.path.expanduser("~/Library/LaunchAgents")
PREFIX = "com.cloudymac.govee."


def main():
    cfg = json.load(open(os.path.join(HERE, "config.json")))
    uid = str(os.getuid())
    for old in [f for f in os.listdir(AGENTS) if f.startswith(PREFIX)] if os.path.isdir(AGENTS) else []:
        subprocess.run(["launchctl", "bootout", f"gui/{uid}", os.path.join(AGENTS, old)], capture_output=True)
        os.remove(os.path.join(AGENTS, old))
    if sys.argv[1:] != ["install"]:
        return print("uninstalled")
    os.makedirs(AGENTS, exist_ok=True)
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
    if os.environ.get("GOVEE_API_KEY"):
        env["GOVEE_API_KEY"] = os.environ["GOVEE_API_KEY"]
    for i, s in enumerate(cfg["schedule"]):
        h, m = map(int, s["time"].split(":"))
        label = f"{PREFIX}{s['action']}.{i}"
        path = os.path.join(AGENTS, label + ".plist")
        plistlib.dump({
            "Label": label,
            "ProgramArguments": [sys.executable or "/usr/bin/python3",
                                 os.path.join(HERE, "govee.py"), "run", s["action"]],
            "StartCalendarInterval": {"Hour": h, "Minute": m},
            "StandardOutPath": "/tmp/govee.log", "StandardErrorPath": "/tmp/govee.log",
            "EnvironmentVariables": env,
        }, open(path, "wb"))
        subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", path], check=False)
        print("installed", label, s["time"])


main()
