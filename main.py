import sys
import os
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import RefreshError
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import itertools
import threading
import time
import calendar as cal
import re
import styling
import signal

os.environ['PYTHONUNBUFFERED'] = '1'


# def spinner(message="Working"):
#     stop = False

#     def run():
#         for c in itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
#             if stop:
#                 break
#             sys.stdout.write(f"\r{styling.dim(message)} {c}")
#             sys.stdout.flush()
#             time.sleep(0.08)
#         sys.stdout.write("\r" + " " * (len(message) + 4) + "\r")

#     thread = threading.Thread(target=run, daemon=True)
#     thread.start()

#     def end():
#         nonlocal stop
#         stop = True
#         thread.join()

#     return end

def spinner(message="Working"):
    print(f"{styling.dim(message)}...")
    return lambda: None

load_dotenv(dotenv_path=Path("gcal") / ".env")
DEFAULT_TZ = os.getenv("DEFAULT_TIMEZONE", "UTC")
TIMEZONE_CHOICES = [t.strip() for t in os.getenv("TIMEZONE_CHOICES", "").split(",") if t.strip()]
QUICK_ACCESS_TIMES = [t.strip() for t in os.getenv("QUICK_ACCESS_TIMES", "").split(",") if t.strip()]
QUICK_ACCESS_DURATIONS = [t.strip() for t in os.getenv("QUICK_ACCESS_DURATIONS", "").split(",") if t.strip()]

COLOR_MAP = {
    key.replace("EVENT_COLOR_", "").replace("_", " "): val
    for key, val in os.environ.items()
    if key.startswith("EVENT_COLOR_")
}

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def authenticate(account_name: str):
    gcal_dir = Path("gcal")
    credentials_path = gcal_dir / "credentials.json"
    token_path = gcal_dir / f"token_{account_name}.json"
    
    if not credentials_path.exists():
        raise FileNotFoundError(styling.err("No credentials.json found in gcal/ directory."))
    
    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            creds = None
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                print(styling.warn(f"Token for '{account_name}' expired. Re-authenticating..."))
                if token_path.exists():
                    token_path.unlink()
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
            token_path.write_text(creds.to_json())
    
    return build("calendar", "v3", credentials=creds)

def pick_account():
    gcal_dir = Path("gcal")
    tokens = sorted([f for f in gcal_dir.glob("token_*.json")])
    
    print(f"\n{styling.h('Which Google account?')}")
    for i, tok in enumerate(tokens, 1):
        account_name = tok.stem.replace("token_", "")
        print(f"[{i}] {account_name}")
    print(f"[{len(tokens) + 1}] Add new account")
    
    choice = input("Enter number: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(tokens):
        return tokens[int(choice)-1].stem.replace("token_", "")
    elif choice.isdigit() and int(choice) == len(tokens) + 1:
        new_name = input("Enter a name for this account (e.g., 'personal', 'work'): ").strip()
        if not new_name:
            raise ValueError("Account name cannot be empty.")
        return new_name
    else:
        raise ValueError("Invalid choice.")

def pick_timezone():
    if not TIMEZONE_CHOICES:
        return DEFAULT_TZ
    print(f"\n{styling.h('Choose a timezone')}")
    for i, tz in enumerate(TIMEZONE_CHOICES, 1):
        print(f"[{i}] {tz}")
    choice = input(f"Enter number (or leave blank for default={DEFAULT_TZ}): ").strip()
    if not choice:
        return DEFAULT_TZ
    if choice.isdigit() and 1 <= int(choice) <= len(TIMEZONE_CHOICES):
        return TIMEZONE_CHOICES[int(choice)-1]
    print(styling.warn("Invalid choice, using default."))
    return DEFAULT_TZ

def format_date_input(user_input: str, tz: ZoneInfo):
    
    if not user_input.strip():
        return None

    parts = user_input.strip().split()
    now = datetime.now()
    
    def parse_recurrence(parts):
        if not parts:
            return None, None, parts

        last = parts[-1].lower()
        
        day_pattern = None
        if len(parts) >= 1:
            potential_pattern = parts[-1].lower()
            if 2 <= len(potential_pattern) <= 7 and all(c in 'mtwrfsu' for c in potential_pattern):
                day_map = {'m': 0, 't': 1, 'w': 2, 'r': 3, 'f': 4, 's': 5, 'u': 6}
                try:
                    days = [day_map[c] for c in potential_pattern]
                    if len(days) == len(set(days)):  # No duplicates
                        day_pattern = days
                        parts = parts[:-1]
                except KeyError:
                    pass
        
        if not parts:
            if day_pattern:
                return "day_pattern", (day_pattern, None), []
            return None, None, []
        
        last = parts[-1].lower()

        if last in ("repeat", "r"):
            return "repeat", 1, parts[:-1]

        m = re.match(r"^(\d+)([dw])$", last)
        if m:
            count = int(m.group(1))
            unit = m.group(2)
            delta = timedelta(days=1) if unit == "d" else timedelta(weeks=1)
            if day_pattern:
                return "day_pattern_count", (day_pattern, count), parts[:-1]
            return "count", (count, delta), parts[:-1]

        for idx in range(len(parts) - 1, -1, -1):
            if parts[idx].lower() in ("d", "w"):
                unit = parts[idx].lower()
                end_date_tokens = parts[idx + 1:]
                parts = parts[:idx]
                delta = timedelta(days=1) if unit == "d" else timedelta(weeks=1)
                if day_pattern:
                    return "day_pattern_until", (day_pattern, end_date_tokens), parts
                return "until", (delta, end_date_tokens), parts
        
        if day_pattern:
            return "day_pattern", (day_pattern, None), parts

        return None, None, parts

    def parse_end_date(tokens):
        if not tokens:
            return None
        result = format_date_input(" ".join(tokens), tz=tz)
        start = result["date"]["start"]
        if "T" in start:
            return datetime.fromisoformat(start)
        else:
            return datetime.fromisoformat(start + "T00:00:00")

    recurrence_mode, recurrence_info, parts = parse_recurrence(parts)
    
    if not parts:
        raise ValueError("No date specified.")
    
    date_part = parts[0]
    time_part = " ".join(parts[1:]) if len(parts) > 1 else None
    
    dt = None
    
    tokens = [p.lower() for p in parts]
    weekdays_map = {day.lower(): i for i, day in enumerate(cal.day_name)}
    aliases = {
        "mon": "monday", "tue": "tuesday", "tues": "tuesday",
        "wed": "wednesday", "weds": "wednesday",
        "thu": "thursday", "thur": "thursday", "thurs": "thursday",
        "fri": "friday", "sat": "saturday", "sun": "sunday",
    }

    def norm_weekday(tok: str):
        return aliases.get(tok.lower(), tok.lower())

    consumed = 0

    if tokens:
        if tokens[0] in ("today",):
            dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
            consumed = 1
        elif tokens[0] in ("tomorrow",):
            dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            consumed = 1
        elif tokens[0] in ("yesterday",):
            dt = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            consumed = 1
        elif tokens[0] in ("this", "next") and len(tokens) >= 2:
            wd_full = norm_weekday(tokens[1])
            if wd_full in weekdays_map:
                target = weekdays_map[wd_full]
                today = now.weekday()

                if tokens[0] == "this":
                    start_of_week = now - timedelta(days=today)
                    candidate = start_of_week + timedelta(days=target)
                    if candidate.date() < now.date():
                        candidate += timedelta(weeks=1)
                    dt = candidate
                else:
                    start_of_next_week = now - timedelta(days=today) + timedelta(weeks=1)
                    dt = start_of_next_week + timedelta(days=target)

                dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                consumed = 2
        elif norm_weekday(tokens[0]) in weekdays_map:
            wd_full = norm_weekday(tokens[0])
            target = weekdays_map[wd_full]
            today = now.weekday()
            days_ahead = (target - today) % 7
            if days_ahead == 0:
                days_ahead = 7
            dt = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
            consumed = 1

    if dt is not None:
        remainder = " ".join(parts[consumed:]).strip()
        time_part = remainder if remainder else None

    if dt is None and date_part.isdigit():
        year_explicit = False

        if len(date_part) == 3:
            month = int(date_part[0])
            day = int(date_part[1:])
            year = now.year
        elif len(date_part) == 4:
            month = int(date_part[:2])
            day = int(date_part[2:])
            year = now.year
        elif len(date_part) == 6:
            month = int(date_part[:2])
            day = int(date_part[2:4])
            yy = int(date_part[4:])
            year = 2000 + yy if yy <= 69 else 1900 + yy
            year_explicit = True
        elif len(date_part) == 8:
            month = int(date_part[:2])
            day = int(date_part[2:4])
            year = int(date_part[4:])
            year_explicit = True
        else:
            month = day = year = None

        if month and day and year:
            dt = datetime(year, month, day)
            if not year_explicit and dt.date() < now.date():
                dt = dt.replace(year=now.year + 1)

    if dt is None:
        for fmt in ("%Y-%m-%d", "%m-%d"):
            try:
                dt = datetime.strptime(date_part, fmt)
                if fmt == "%m-%d":
                    dt = dt.replace(year=now.year)
                    if dt.date() < now.date():
                        dt = dt.replace(year=now.year + 1)
                break
            except ValueError:
                continue

    if dt is None:
        raise ValueError("Invalid date. Examples: '2025-08-17', '08-17', '817', '0817'; also 'today', 'tuesday', 'this fri', 'next wed'.")

    def build_recurrences(dt):
        if not recurrence_mode:
            return [dt]

        if recurrence_mode == "repeat":
            return [dt, dt + timedelta(weeks=1)]

        if recurrence_mode == "count":
            count, delta = recurrence_info
            return [dt + i * delta for i in range(count)]

        if recurrence_mode == "until":
            delta, end_tokens = recurrence_info
            end_dt = parse_end_date(end_tokens)
            if not end_dt:
                return [dt]

            MAX_RECURRENCES = 200
            dates = []
            cur = dt
            while cur.date() <= end_dt.date():
                if len(dates) >= MAX_RECURRENCES:
                    raise ValueError(f"Recurrence exceeds {MAX_RECURRENCES} entries.")
                dates.append(cur)
                cur += delta
            return dates
        
        if recurrence_mode in ("day_pattern", "day_pattern_count", "day_pattern_until"):
            if recurrence_mode == "day_pattern":
                days, _ = recurrence_info
                # Default to 4 weeks
                end_dt = dt + timedelta(weeks=4)
            elif recurrence_mode == "day_pattern_count":
                days, count = recurrence_info
                dates = []
                cur = dt
                while len(dates) < count:
                    if cur.weekday() in days:
                        dates.append(cur)
                    cur += timedelta(days=1)
                return dates
            else:  
                days, end_tokens = recurrence_info
                end_dt = parse_end_date(end_tokens)
                if not end_dt:
                    end_dt = dt + timedelta(weeks=4)
            
            MAX_RECURRENCES = 200
            dates = []
            cur = dt
            while cur.date() <= end_dt.date():
                if len(dates) >= MAX_RECURRENCES:
                    raise ValueError(f"Recurrence exceeds {MAX_RECURRENCES} entries.")
                if cur.weekday() in days:
                    dates.append(cur)
                cur += timedelta(days=1)
            return dates

        return [dt]

    # ── Parse time ──
    if time_part:
        for time_fmt in ("%H:%M", "%I:%M %p"):
            try:
                t = datetime.strptime(time_part, time_fmt)
                dt = dt.replace(hour=t.hour, minute=t.minute, tzinfo=tz)
                dates = build_recurrences(dt)
                return {
                    "date": {"start": dates[0].isoformat()},
                    "_recurrences": dates[1:]
                }
            except ValueError:
                pass

        m = re.match(r"^\s*(\d{1,4})\s*(am|pm|AM|PM)?\s*$", time_part)
        if m:
            digits = m.group(1)
            ampm = (m.group(2) or "").lower()

            if len(digits) in (3, 4):
                hour = int(digits[:-2])
                minute = int(digits[-2:])
            elif len(digits) in (1, 2):
                hour = int(digits)
                minute = 0
            else:
                raise ValueError("Time too long. Use up to 4 digits, e.g. '232' or '1259'.")

            if not (0 <= minute <= 59):
                raise ValueError("Minute must be 00–59.")
            if ampm:
                if not (1 <= hour <= 12):
                    raise ValueError("Hour must be 1–12 when using AM/PM.")
                if ampm == "am":
                    hour = 0 if hour == 12 else hour
                else:
                    hour = 12 if hour == 12 else hour + 12
            else:
                if not (0 <= hour <= 23):
                    raise ValueError("Hour must be 00–23 for 24-hour times.")

            dt = dt.replace(hour=hour, minute=minute, tzinfo=tz)
            dates = build_recurrences(dt)
            return {
                "date": {"start": dates[0].isoformat()},
                "_recurrences": dates[1:]
            }

        raise ValueError("Invalid time. Examples: '14:30', '2:30 PM', '232', '1259', or '232 PM'.")

    if QUICK_ACCESS_TIMES:
        print(f"\n{styling.dim('Choose a time or leave blank for no time:')}")
        for i, t in enumerate(QUICK_ACCESS_TIMES, 1):
            print(f"[{i}] {t}")
        choice = input("Enter number or blank: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(QUICK_ACCESS_TIMES):
            t_str = QUICK_ACCESS_TIMES[int(choice) - 1]
            for time_fmt in ("%H:%M", "%I:%M %p"):
                try:
                    t = datetime.strptime(t_str, time_fmt)
                    dt = dt.replace(hour=t.hour, minute=t.minute, tzinfo=tz)
                    dates = build_recurrences(dt)
                    return {
                        "date": {"start": dates[0].isoformat()},
                        "_recurrences": dates[1:]
                    }
                except ValueError:
                    continue

    dates = build_recurrences(dt)
    return {
        "date": {"start": dates[0].date().isoformat()},
        "_recurrences": [d.date().isoformat() for d in dates[1:]]
    }

def parse_duration(duration_str):
    """Parse duration string like '1 hr', '30 min', '1.5 hrs', '90 min' into timedelta."""
    duration_str = duration_str.lower().strip()
    
    # Match patterns like "1 hr", "30 min", "1.5 hrs", "90 minutes"
    m = re.match(r"^([\d.]+)\s*(hr|hrs?|hour|hours?|min|mins?|minute|minutes?)$", duration_str)
    if not m:
        return None
    
    value = float(m.group(1))
    unit = m.group(2)
    
    if unit.startswith("hr") or unit.startswith("hour"):
        return timedelta(hours=value)
    elif unit.startswith("min"):
        return timedelta(minutes=value)
    
    return None

def show_examples():
    """Display comprehensive usage examples."""
    print(f"\n{styling.h('Usage Examples')}\n")
    
    print(f"{styling.h('REGULAR EVENTS (with time)')}")
    print(f"  {styling.dim('Start:')} today 2pm          {styling.dim('→ Today at 2:00 PM')}")
    print(f"  {styling.dim('Start:')} tomorrow 9:30 am    {styling.dim('→ Tomorrow at 9:30 AM')}")
    print(f"  {styling.dim('Start:')} 0315 1400          {styling.dim('→ March 15 at 2:00 PM (14:00)')}")
    print(f"  {styling.dim('Start:')} monday 10am        {styling.dim('→ Next Monday at 10:00 AM')}")
    print(f"  {styling.dim('Start:')} this fri 3pm       {styling.dim('→ This Friday at 3:00 PM')}")
    print(f"  {styling.dim('Start:')} 2025-08-17 11:59 pm {styling.dim('→ Aug 17, 2025 at 11:59 PM')}\n")
    
    print(f"{styling.h('ALL-DAY EVENTS (no time)')}")
    print(f"  {styling.dim('Start:')} today              {styling.dim('→ All day today')}")
    print(f"  {styling.dim('Start:')} 0420               {styling.dim('→ All day April 20')}")
    print(f"  {styling.dim('Start:')} next wednesday     {styling.dim('→ All day next Wednesday')}\n")
    
    print(f"{styling.h('RECURRING EVENTS')}\n")
    
    print(f"{styling.dim('Simple Repeat (once more, +1 week):')}")
    print(f"  {styling.dim('Start:')} monday 9am repeat")
    print(f"  {styling.dim('Start:')} friday 6pm r\n")
    
    print(f"{styling.dim('Count-based (X occurrences):')}")
    print(f"  {styling.dim('Start:')} today 2pm 5d       {styling.dim('→ 5 daily occurrences')}")
    print(f"  {styling.dim('Start:')} monday 10am 3w     {styling.dim('→ 3 weekly occurrences')}\n")
    
    print(f"{styling.dim('Until Date (repeat until specific date):')}")
    print(f"  {styling.dim('Start:')} today 9am d 0315   {styling.dim('→ Daily until March 15')}")
    print(f"  {styling.dim('Start:')} monday 2pm w 0501  {styling.dim('→ Weekly until May 1')}\n")
    
    print(f"{styling.dim('Day Patterns (specific days of week):')}")
    print(f"  {styling.dim('Start:')} monday 9am mwf     {styling.dim('→ Mon/Wed/Fri for 4 weeks (default)')}")
    print(f"  {styling.dim('Start:')} tuesday 10am tth   {styling.dim('→ Tue/Thu for 4 weeks')}")
    print(f"  {styling.dim('Start:')} today 3pm mw       {styling.dim('→ Mon/Wed for 4 weeks')}")
    print(f"  {styling.dim('Start:')} friday 1pm tr      {styling.dim('→ Tue/Thu for 4 weeks')}\n")
    
    print(f"{styling.dim('Day Pattern Codes:')}")
    print(f"  m=Mon, t=Tue, w=Wed, r=Thu, f=Fri, s=Sat, u=Sun")
    print(f"  {styling.dim('Examples:')} mwf, tth, mw, tr, mtwrf (weekdays), su (weekends)\n")
    
    print(f"{styling.dim('Combined (day pattern + end date):')}")
    print(f"  {styling.dim('Start:')} monday 9am mwf d 0515    {styling.dim('→ Mon/Wed/Fri until May 15')}")
    print(f"  {styling.dim('Start:')} today 2pm tth d 0401     {styling.dim('→ Tue/Thu until April 1')}\n")
    
    print(f"{styling.h('REAL-WORLD EXAMPLES')}\n")
    
    print(f"{styling.dim('College class (MWF 9-10am, ends May 15):')}")
    print(f"  Title: CS 101 - Intro to Programming")
    print(f"  Start: monday 9am mwf d 0515")
    print(f"  End: monday 10am mwf d 0515\n")
    
    print(f"{styling.dim('Gym routine (Mon/Wed/Fri for 8 weeks):')}")
    print(f"  Title: Workout")
    print(f"  Start: monday 6am mwf w 0315")
    print(f"  End: monday 7am mwf w 0315\n")
    
    print(f"{styling.dim('Daily standup (every weekday, 10 occurrences):')}")
    print(f"  Title: Team Standup")
    print(f"  Start: today 10am 10d")
    print(f"  End: today 10:15 am 10d\n")
    
    print(f"{styling.dim('Weekly meeting (every Thursday for 5 weeks):')}")
    print(f"  Title: Project Review")
    print(f"  Start: thursday 2pm 5w")
    print(f"  End: thursday 3pm 5w\n")
    
    input(f"{styling.dim('Press Enter to continue...')}")

def prompt_event_details(tz):
    print(f"\n{styling.h('=== Add a New Calendar Event ===')}")
    
    # Offer to show examples
    show_help = input(f"{styling.dim('Show usage examples? (y/n):')} ").strip().lower()
    if show_help in ("y", "yes"):
        show_examples()
    
    title = input("\nTitle: ").strip()

    print(f"\n{styling.dim('Date formats: 2025-08-17, 08-17, 817, today, tomorrow, monday, this fri, next wed')}")
    print(f"{styling.dim('Time formats: 14:30, 2:30 PM, 232, 1259, 232 PM')}")
    print(f"{styling.dim('Recurrence: repeat/r, 5d, 3w, d 0315, w 0401, mwf (Mon/Wed/Fri), tth, mwf d 0315')}")
    
    while True:
        try:
            start_dict = format_date_input(input("\nStart date/time: "), tz=tz)
            break
        except ValueError as e:
            print(styling.err(str(e)))
    
    # Check if we should offer quick durations
    start_str = start_dict["date"]["start"]
    has_time = "T" in start_str
    
    if has_time and QUICK_ACCESS_DURATIONS:
        print(f"\n{styling.dim('Choose a duration or enter custom end time:')}")
        for i, dur in enumerate(QUICK_ACCESS_DURATIONS, 1):
            print(f"[{i}] {dur}")
        choice = input("Enter number or custom end time: ").strip()
        
        if choice.isdigit() and 1 <= int(choice) <= len(QUICK_ACCESS_DURATIONS):
            # Apply duration to start time
            dur_str = QUICK_ACCESS_DURATIONS[int(choice) - 1]
            delta = parse_duration(dur_str)
            if delta:
                start_dt = datetime.fromisoformat(start_str)
                end_dt = start_dt + delta
                end_dict = {
                    "date": {"start": end_dt.isoformat()},
                    "_recurrences": [dt + delta if isinstance(dt, datetime) else dt 
                                   for dt in start_dict.get("_recurrences", [])]
                }
            else:
                print(styling.warn(f"Invalid duration format: {dur_str}. Please enter end time manually."))
                while True:
                    try:
                        end_dict = format_date_input(input("End date/time: "), tz=tz)
                        break
                    except ValueError as e:
                        print(styling.err(str(e)))
        else:
            # Custom end time
            while True:
                try:
                    end_dict = format_date_input(choice if choice else input("End date/time: "), tz=tz)
                    break
                except ValueError as e:
                    print(styling.err(str(e)))
                    choice = ""
    else:
        while True:
            try:
                end_dict = format_date_input(input("End date/time: "), tz=tz)
                break
            except ValueError as e:
                print(styling.err(str(e)))

    location = input("\nLocation (optional): ").strip()
    description = input("Description (optional): ").strip()

    color_id = None

    if COLOR_MAP:
        print(f"\n{styling.dim('Choose a label or leave blank:')}")
        labels = list(COLOR_MAP.keys())
        for i, lbl in enumerate(labels, 1):
            print(f"[{i}] {lbl}")

        choice = input("Enter number: ").strip().lower()

        if choice.isdigit() and 1 <= int(choice) <= len(labels):
            color_id = COLOR_MAP[labels[int(choice) - 1]]
    else:
        label = input("Label (for color mapping, optional): ").strip().lower()
        color_id = COLOR_MAP.get(label)


    start_str = start_dict["date"]["start"]
    end_str = end_dict["date"]["start"]
    
    start_recurrences = start_dict.get("_recurrences", [])
    end_recurrences = end_dict.get("_recurrences", [])

    if "T" in start_str:
        event_start = {"dateTime": start_str, "timeZone": DEFAULT_TZ}
        event_end = {"dateTime": end_str, "timeZone": DEFAULT_TZ}
    else:
        event_start = {"date": start_str}
        event_end = {"date": end_str}

    return {
        "summary": title,
        "start": event_start,
        "end": event_end,
        "location": location or None,
        "description": description or None,
        "colorId": color_id,
        "_start_recurrences": start_recurrences,
        "_end_recurrences": end_recurrences,
    }

def add_events(service, event_template):
    """Add event(s) to calendar, handling recurrences."""
    start_recurrences = event_template.pop("_start_recurrences", [])
    end_recurrences = event_template.pop("_end_recurrences", [])
    
    total = 1 + len(start_recurrences)
    
    if total > 1:
        print(f"\n{styling.dim(f'This will create {total} events.')}")
        confirm = input("Continue? (y/n): ").strip().lower()
        if confirm not in ("y", "yes"):
            print(styling.warn("Cancelled."))
            return
    
    events_created = []
    stop_spinner = spinner(f"Creating {'event' if total == 1 else 'events'}...")
    
    try:
        # Create first event
        created = service.events().insert(calendarId="primary", body=event_template).execute()
        events_created.append(created)
        
        # Create recurring events
        for i, start_dt in enumerate(start_recurrences):
            end_dt = end_recurrences[i] if i < len(end_recurrences) else start_dt
            
            dup_event = dict(event_template)
            
            if isinstance(start_dt, datetime):
                dup_event["start"] = {"dateTime": start_dt.isoformat(), "timeZone": DEFAULT_TZ}
                dup_event["end"] = {"dateTime": end_dt.isoformat(), "timeZone": DEFAULT_TZ}
            else:
                dup_event["start"] = {"date": start_dt}
                dup_event["end"] = {"date": end_dt}
            
            created = service.events().insert(calendarId="primary", body=dup_event).execute()
            events_created.append(created)
    
    finally:
        stop_spinner()
    
    # Summary
    print(f"\n{styling.ok(f'✓ Created {len(events_created)} event(s)!')}")
    print(f"{styling.dim('Title:')} {event_template['summary']}")
    
    start = event_template['start'].get('dateTime') or event_template['start'].get('date')
    end = event_template['end'].get('dateTime') or event_template['end'].get('date')
    print(f"{styling.dim('When:')} {start} → {end}")
    
    if event_template.get("location"):
        print(f"{styling.dim('Location:')} {event_template['location']}")
    if event_template.get("description"):
        print(f"{styling.dim('Description:')} {event_template['description']}")
    if event_template.get("colorId"):
        print(f"{styling.dim('Color ID:')} {event_template['colorId']}")
    
    print(f"\n{styling.dim('Links:')}")
    for evt in events_created[:3]:  # Show first 3
        print(f"  {evt.get('htmlLink')}")
    if len(events_created) > 3:
        print(f"  {styling.dim(f'... and {len(events_created) - 3} more')}")

def main():
    # Pick timezone once at start
    while True:
        try:
            tz = ZoneInfo(pick_timezone())
            break
        except KeyboardInterrupt:
            try:
                confirm = input("\nAre you sure you want to quit? (y/n): ").strip().lower()
            except KeyboardInterrupt:
                print(f"\n{styling.ok('Goodbye!')}")
                sys.exit(0)
            if confirm in ("y", "yes"):
                print(styling.ok("Goodbye!"))
                sys.exit(0)
            else:
                print(styling.ok("Resuming..."))
    
    # Pick account
    while True:
        try:
            account_name = pick_account()
            service = authenticate(account_name)
            break
        except KeyboardInterrupt:
            try:
                confirm = input("\nAre you sure you want to quit? (y/n): ").strip().lower()
            except KeyboardInterrupt:
                print(f"\n{styling.ok('Goodbye!')}")
                sys.exit(0)
            if confirm in ("y", "yes"):
                print(styling.ok("Goodbye!"))
                sys.exit(0)
            else:
                print(styling.ok("Resuming..."))

    while True:
        try:
            event = prompt_event_details(tz)
            add_events(service, event)

            again = input(
                f"\n{styling.dim('Add another? (y = same account / s = switch account / n = quit):')} "
            ).strip().lower()

            if again in ("y", "yes"):
                continue
            elif again in ("s", "switch"):
                account_name = pick_account()
                service = authenticate(account_name)
            else:
                print(styling.ok("Done."))
                break
        except KeyboardInterrupt:
            try:
                confirm = input("\nAre you sure you want to quit? (y/n): ").strip().lower()
            except KeyboardInterrupt:
                print(f"\n{styling.ok('Goodbye!')}")
                sys.exit(0)
            if confirm in ("y", "yes"):
                print(styling.ok("Goodbye!"))
                sys.exit(0)
            else:
                print(styling.ok("Resuming..."))

if __name__ == "__main__":
    main()
