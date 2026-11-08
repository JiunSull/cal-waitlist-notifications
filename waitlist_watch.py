#!/usr/bin/env python3
"""
Watch Berkeley class enrollment and notify on changes.

Notifies (macOS notification + optional phone push via ntfy.sh) when:
  - the waitlist count changes (e.g. 10 -> 9 means a spot opened)
  - a seat opens up in a full class, or the class fills
  - the seat cap or waitlist cap changes (department added seats)

Usage:
  python3 waitlist_watch.py           # run forever, checking every check_every_min
  python3 waitlist_watch.py --once    # check once and exit (prints current numbers)
  python3 waitlist_watch.py --test    # send a test notification and exit

Reads the official public class page on classes.berkeley.edu (falls back to
Berkeleytime if that page can't be read).
"""

import json
import os
import subprocess
import sys
import time
import re
from datetime import datetime
from pathlib import Path

# ------------------------------------------------------------------ config ---
# Settings live in config.json next to this script (copy config.example.json).
# The ntfy topic comes from the NTFY_TOPIC environment variable so it never
# ends up in git: anyone who knows a topic name can read and post to it.

CONFIG_FILE = Path(os.environ.get("WAITLIST_CONFIG", Path(__file__).with_name("config.json")))
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()


def load_config(path=CONFIG_FILE):
    try:
        cfg = json.loads(Path(path).read_text())
    except FileNotFoundError:
        sys.exit(f"No config found at {path}. Copy config.example.json to config.json and edit it.")
    except ValueError as e:
        sys.exit(f"{path} isn't valid JSON: {e}")
    classes = [(c["subject"].upper(), str(c["number"]).upper(), str(c.get("section", "001")).zfill(3),
                c.get("label") or f"{c['subject']} {c['number']}") for c in cfg["classes"]]
    return {
        "year": int(cfg["year"]),
        "semester": cfg["semester"].capitalize(),
        "classes": classes,
        "check_every_min": max(2, int(cfg.get("check_every_min", 5))),
        "notify_enrolled_changes": bool(cfg.get("notify_enrolled_changes", False)),
    }


CFG = None  # filled in by main()

CLASS_PAGE = "https://classes.berkeley.edu/content/{year}-{sem}-{subj}-{num}-{sec}-lec-{sec}"
API = "https://berkeleytime.com/api/graphql"
# The persisted-query id Berkeleytime's own enrollment page uses. If Berkeleytime
# ships a new version this can stop working; the script will notify you if so.
QUERY_ID = "6b4e761f02e20db683488a9928ee2b8c6d07dbddab14851410cd0e94e2585382"
STATE_FILE = Path.home() / ".waitlist_watch_state.json"
LOG_FILE = Path.home() / "Library" / "Logs" / "waitlist_watch.log"


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def notify(title, message):
    log(f"NOTIFY  {title}: {message}")
    # macOS banner with a sound
    script = f'display notification {json.dumps(message)} with title {json.dumps(title)} sound name "Glass"'
    subprocess.run(["osascript", "-e", script], check=False)
    if NTFY_TOPIC:
        out = subprocess.run(
            ["/usr/bin/curl", "-sS", "--fail", "-m", "15",
             "-H", f"Title: {title}", "-H", "Priority: high", "-H", "Tags: rotating_light",
             "--data-binary", "@-", f"https://ntfy.sh/{NTFY_TOPIC}"],
            input=message.encode(), capture_output=True, check=False,
        )
        if out.returncode != 0:
            log(f"ntfy push failed: {out.stderr.decode().strip()[:200]}")


def fetch_berkeleytime(subject, number, section):
    body = json.dumps({
        "id": QUERY_ID,
        "variables": {
            "year": CFG["year"], "semester": CFG["semester"], "sessionId": "1",
            "subject": subject, "courseNumber": number, "sectionNumber": section,
        },
    }).encode()
    # Uses macOS's built-in curl (system certificates) instead of Python's SSL,
    # which often lacks root certificates on Mac Python installs.
    out = subprocess.run(
        ["/usr/bin/curl", "-sS", "--fail", "-m", "30", "-X", "POST", API,
         "-H", "content-type: application/json",
         "-H", "accept: application/graphql-response+json,application/json;q=0.9",
         "-H", "apollo-require-preflight: true",
         "-A", "waitlist-watch/1.0 (personal script)",
         "--data-binary", "@-"],
        input=body, capture_output=True, check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"curl failed ({out.returncode}): {out.stderr.decode().strip()[:200]}")
    data = json.loads(out.stdout)
    hist = (((data or {}).get("data") or {}).get("enrollment") or {}).get("history") or []
    if not hist:
        raise RuntimeError(f"no enrollment data returned: {json.dumps(data)[:200]}")
    p = hist[-1]
    return {
        "enrolled": p["enrolledCount"], "cap": p["maxEnroll"],
        "waitlisted": p["waitlistedCount"], "waitlist_cap": p["maxWaitlist"],
        "as_of": p.get("endTime") or p.get("startTime"),
    }


def curl_get(url):
    out = subprocess.run(
        ["/usr/bin/curl", "-sS", "--fail", "-L", "-m", "30",
         "-H", "Cache-Control: no-cache", "-A", "waitlist-watch/1.0 (personal script)", url],
        capture_output=True, check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"curl failed ({out.returncode}): {out.stderr.decode().strip()[:200]}")
    return out.stdout.decode("utf-8", "replace")


def fetch_class_page(subject, number, section):
    """Read the official public class page on classes.berkeley.edu."""
    url = CLASS_PAGE.format(year=CFG["year"], sem=CFG["semester"].lower(), subj=subject.lower(),
                            num=number.lower(), sec=section)
    html = curl_get(f"{url}?nocache={int(time.time())}")
    i = html.find("current-enrollment")
    if i < 0:
        raise RuntimeError("no Current Enrollment section on the class page")
    block = html[i:i + 3000]

    def num(label):
        m = re.search(label + r":</strong>\s*(?:<span>)?\s*(\d+)", block)
        if not m:
            raise RuntimeError(f"couldn't find '{label}' on the class page")
        return int(m.group(1))

    return {"enrolled": num("Enrolled"), "cap": num("Capacity"),
            "waitlisted": num("Waitlisted"), "waitlist_cap": num("Waitlist Max"),
            "as_of": datetime.now().isoformat(timespec="seconds"), "source": "classes.berkeley.edu"}


def fetch(subject, number, section):
    try:
        return fetch_class_page(subject, number, section)
    except Exception as e:  # noqa: BLE001
        log(f"class page failed ({e}); falling back to Berkeleytime")
        d = fetch_berkeleytime(subject, number, section)
        d["source"] = "berkeleytime"
        return d


def describe(s):
    return (f"{s['enrolled']}/{s['cap']} enrolled, "
            f"waitlist {s['waitlisted']}/{s['waitlist_cap']}")


def changes(label, old, new, notify_enrolled=False):
    msgs = []
    if old is None:
        return msgs
    if new["waitlisted"] != old["waitlisted"]:
        if (old["waitlist_cap"] and old["waitlisted"] >= old["waitlist_cap"]
                and new["waitlisted"] < new["waitlist_cap"]):
            free = new["waitlist_cap"] - new["waitlisted"]
            msgs.append(f"WAITLIST SPOT OPEN ({free} free): waitlist "
                        f"{old['waitlisted']} → {new['waitlisted']}/{new['waitlist_cap']}. Go now!")
        else:
            msgs.append(f"Waitlist {old['waitlisted']} → {new['waitlisted']}/{new['waitlist_cap']}")
    seat_event = ((old["enrolled"] >= old["cap"] > 0 and new["enrolled"] < new["cap"])
                  or (old["enrolled"] < old["cap"] and new["enrolled"] >= new["cap"] > 0))
    if notify_enrolled and new["enrolled"] != old["enrolled"] and not seat_event:
        msgs.append(f"Enrolled {old['enrolled']} → {new['enrolled']}/{new['cap']} "
                    f"({new['cap'] - new['enrolled']} seats left)")
    if old["enrolled"] >= old["cap"] > 0 and new["enrolled"] < new["cap"]:
        msgs.append(f"SEAT OPEN: {new['enrolled']}/{new['cap']} enrolled. Go now!")
    elif old["enrolled"] < old["cap"] and new["enrolled"] >= new["cap"] > 0:
        msgs.append(f"Class just filled ({new['enrolled']}/{new['cap']})")
    if new["cap"] != old["cap"]:
        msgs.append(f"Seat cap changed {old['cap']} → {new['cap']}")
    if new["waitlist_cap"] != old["waitlist_cap"]:
        msgs.append(f"Waitlist cap changed {old['waitlist_cap']} → {new['waitlist_cap']}")
    return msgs


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def check(state, quiet_first=True):
    for subject, number, section, label in CFG["classes"]:
        key = f"{subject} {number} {section}"
        try:
            new = fetch(subject, number, section)
        except Exception as e:  # noqa: BLE001
            fails = state.get("_fails", {}).get(key, 0) + 1
            state.setdefault("_fails", {})[key] = fails
            log(f"{label}: check failed ({fails}x): {e}")
            if fails == 3:  # tell you once if it keeps failing
                notify(f"{label} watcher", "Checks keep failing; the class page or Berkeleytime may have changed. See the log.")
            continue
        state.setdefault("_fails", {})[key] = 0
        old = state.get(key)
        log(f"{label}: {describe(new)}  [{new.get('source', '')}]")
        if not quiet_first:
            notify(label, f"Now watching: {describe(new)}")
        for m in changes(label, old, new, CFG["notify_enrolled_changes"]):
            notify(label, m)
        state[key] = new
    STATE_FILE.write_text(json.dumps(state, indent=1))


def main():
    global CFG
    if "--test" in sys.argv:
        notify("Waitlist watcher", "Test notification: notifications are working.")
        return
    CFG = load_config()
    state = load_state()
    if "--once" in sys.argv:
        check(state, quiet_first=True)
        return
    every = CFG["check_every_min"]
    log(f"Watching {', '.join(c[3] for c in CFG['classes'])} every {every} min")
    first = True
    while True:
        check(state, quiet_first=not first)
        first = False
        time.sleep(every * 60)


if __name__ == "__main__":
    main()
