# Cal Waitlist Notifications

Get a notification the moment a UC Berkeley class waitlist moves.

During Phase 2, popular classes sit at a full waitlist (say 10/10) and a spot only opens when someone drops, often for just a few minutes. This script checks the class every few minutes and alerts you on your Mac (and optionally your phone) when:

- a **waitlist spot opens** (e.g. 10 → 9)
- a **seat opens** in a full class
- the class **fills**
- the department **changes the seat or waitlist cap** (e.g. adds seats in January)

```
2026-11-03 16:05:12  Physics 105: 70/70 enrolled, waitlist 10/10  [classes.berkeley.edu]
2026-11-03 16:10:14  NOTIFY  Physics 105: WAITLIST SPOT OPEN (1 free): waitlist 10 → 9/10. Go now!
```

## How it works

1. Reads the **Current Enrollment** section of the public class page on [classes.berkeley.edu](https://classes.berkeley.edu) (enrolled, capacity, waitlisted, waitlist max).
2. If that page can't be read, falls back to the enrollment data behind [Berkeleytime](https://berkeleytime.com)'s charts.
3. Compares against the last check (saved in `~/.waitlist_watch_state.json`) and sends a notification for each meaningful change.
4. Runs in the background as a macOS launchd agent, so it keeps going after you close Terminal and restarts after a reboot.

Requests go through the system `curl` rather than Python's `urllib`, since many Mac Python installs ship without root certificates.

## Setup (macOS)

```bash
git clone https://github.com/JiunSull/cal-waitlist-notifications.git
cd cal-waitlist-notifications
cp config.example.json config.json      # then edit: term + classes to watch
python3 waitlist_watch.py --test        # should pop a notification
python3 waitlist_watch.py --once        # prints current numbers, no notifications
bash install.sh                         # run in the background
```

The first time, macOS may ask whether Script Editor can send notifications. Allow it, and set its style to **Alerts** in System Settings → Notifications so they stay on screen.

### Phone notifications (optional)

1. Install the free [ntfy](https://ntfy.sh) app and subscribe to a topic name nobody would guess.
2. Install with that topic: `NTFY_TOPIC=your-secret-topic bash install.sh`

The topic is passed as an environment variable so it never ends up in the repo. Anyone who knows a topic name can read it.

### Stop it

```bash
bash install.sh --uninstall
```

## Config

`config.json`:

| Key | Meaning |
|---|---|
| `year`, `semester` | Term to watch, e.g. `2027`, `"Spring"` |
| `classes` | List of `{subject, number, section, label}`. `subject` and `number` match the class URL, e.g. `COMPSCI` / `188` / `001` |
| `check_every_min` | Minutes between checks (minimum 2). Please keep this modest |
| `notify_enrolled_changes` | `true` also notifies on every enrollment change (noisy while seats are open) |

After editing the config, rerun `bash install.sh` to update the background copy.

## Tests

```bash
python3 -m unittest discover tests
```

## Limitations

- **Not official.** It reads public pages, and Berkeleytime's internal API as a fallback. Either can change without notice. If checks fail three times in a row, it sends one alert so you know.
- **Can lag.** Numbers are only as fresh as the public pages, so a spot can be taken before you see it.
- **macOS only** for desktop notifications (it uses `osascript` and launchd). ntfy works anywhere.
- **Only while your Mac is awake.**
- Doesn't log in to CalCentral and never asks for your CalNet credentials. You still enroll yourself.
