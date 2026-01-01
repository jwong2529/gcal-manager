import os
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from zoneinfo import ZoneInfo
from datetime import datetime
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

load_dotenv()
DEFAULT_TZ = os.getenv("DEFAULT_TIMEZONE", "UTC")
TIMEZONE_CHOICES = [t.strip() for t in os.getenv("TIMEZONE_CHOICES", "").split(",") if t.strip()]
QUICK_ACCESS_TIMES = [t.strip() for t in os.getenv("QUICK_ACCESS_TIMES", "").split(",") if t.strip()]

# Label → Google colorId (1–11) mapping from .env
COLOR_MAP = {
    key.replace("EVENT_COLOR_", "").lower(): val
    for key, val in os.environ.items()
    if key.startswith("EVENT_COLOR_")
}

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def authenticate(account_name: str):
    gcal_dir = Path("gcal")
    credentials_path = gcal_dir / "credentials.json"
    token_path = gcal_dir / f"token_{account_name}.json"
    
    if not credentials_path.exists():
        raise FileNotFoundError("⚠️ No credentials.json found in gcal/ directory.")
    
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        
        # save credentials for next time
        token_path.write_text(creds.to_json())
    
    return build("calendar", "v3", credentials=creds)

def pick_account():
    gcal_dir = Path("gcal")
    tokens = sorted([f for f in gcal_dir.glob("token_*.json")])
    
    print("\nWhich Google account?")
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
    print("\nChoose a timezone:")
    for i, tz in enumerate(TIMEZONE_CHOICES, 1):
        print(f"[{i}] {tz}")
    choice = input(f"Enter number (or leave blank for default={DEFAULT_TZ}): ").strip()
    if not choice:
        return DEFAULT_TZ
    if choice.isdigit() and 1 <= int(choice) <= len(TIMEZONE_CHOICES):
        return TIMEZONE_CHOICES[int(choice)-1]
    print("Invalid choice, using default.")
    return DEFAULT_TZ

def format_date_input(user_input: str):
    import re
    import calendar
    from datetime import timedelta

    if not user_input.strip():
        return None

    # Original split (kept)
    parts = user_input.strip().split()
    date_part = parts[0]
    time_part = " ".join(parts[1:]) if len(parts) > 1 else None
    tz = ZoneInfo(pick_timezone())

    now = datetime.now()
    dt = None  

    tokens = [p.lower() for p in parts]
    weekdays_map = {day.lower(): i for i, day in enumerate(calendar.day_name)}
    aliases = {
        "mon": "monday",
        "tue": "tuesday", "tues": "tuesday",
        "wed": "wednesday", "weds": "wednesday",
        "thu": "thursday", "thur": "thursday", "thurs": "thursday",
        "fri": "friday",
        "sat": "saturday",
        "sun": "sunday",
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
            dt = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
            consumed = 1

    if dt is not None:
        remainder = " ".join(parts[consumed:]).strip()
        time_part = remainder if remainder else None

    if dt is None and date_part.isdigit() and len(date_part) in (3, 4):
        if len(date_part) == 3:   
            month = int(date_part[0])
            day = int(date_part[1:])
        else:                  
            month = int(date_part[:2])
            day = int(date_part[2:])
        dt = datetime(now.year, month, day)

    if dt is None:
        for fmt in ("%Y-%m-%d", "%m-%d"):
            try:
                dt = datetime.strptime(date_part, fmt)
                if fmt == "%m-%d":
                    dt = dt.replace(year=now.year)
                break
            except ValueError:
                continue

    if dt is None:
        raise ValueError("Invalid date. Examples: '2025-08-17', '08-17', '817', or '0817'; also 'today', 'tuesday', 'this fri', 'next wed'.")

    if time_part:
        for time_fmt in ("%H:%M", "%I:%M %p"):
            try:
                t = datetime.strptime(time_part, time_fmt)
                dt = dt.replace(hour=t.hour, minute=t.minute, tzinfo=tz)
                return {"date": {"start": dt.isoformat()}}
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
            return {"date": {"start": dt.isoformat()}}

        raise ValueError(
            "Invalid time. Examples: '14:30', '2:30 PM', '232', '1259', or '232 PM'."
        )

    if QUICK_ACCESS_TIMES:
        print("\nChoose a hardcoded time or leave blank for no time:")
        for i, t in enumerate(QUICK_ACCESS_TIMES, 1):
            print(f"[{i}] {t}")
        choice = input("Enter number or blank: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(QUICK_ACCESS_TIMES):
            t_str = QUICK_ACCESS_TIMES[int(choice) - 1]
            for time_fmt in ("%H:%M", "%I:%M %p"):
                try:
                    t = datetime.strptime(t_str, time_fmt)
                    dt = dt.replace(hour=t.hour, minute=t.minute, tzinfo=tz)
                    return {"date": {"start": dt.isoformat()}}
                except ValueError:
                    continue
        return {"date": {"start": dt.date().isoformat()}}

    return {"date": {"start": dt.date().isoformat()}}

def prompt_event_details():
    print("\n=== Add a New Calendar Event ===")
    title = input("Title: ").strip()

    while True:
        try:
            start_dict = format_date_input(input("Start date/time: "))
            end_dict = format_date_input(input("End date/time: "))
            break
        except ValueError as e:
            print(f"{e}. Try again.")

    location = input("Location (optional): ").strip()
    description = input("Description (optional): ").strip()

    label = input("Label (for color mapping, optional): ").strip().lower()
    color_id = COLOR_MAP.get(label)

    start_str = start_dict["date"]["start"]
    end_str = end_dict["date"]["start"]

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
    }

def add_event(service, event):
    created = service.events().insert(calendarId="primary", body=event).execute()
    print("\nEvent created!")
    print(f"   Title: {created['summary']}")
    
    start = event['start'].get('dateTime') or event['start'].get('date')
    end = event['end'].get('dateTime') or event['end'].get('date')
    print(f"   When:  {start} → {end}")
    
    if event.get("location"):
        print(f"   Location: {event['location']}")
    if event.get("description"):
        print(f"   Description: {event['description']}")
    if event.get("colorId"):
        print(f"   Color ID: {event['colorId']}")
    print(f"   Link: {created.get('htmlLink')}")

def main():
    account_name = pick_account()
    service = authenticate(account_name)

    while True:
        event = prompt_event_details()
        add_event(service, event)

        again = input(
            "\n➕ Add another? (y = same account / s = switch account / n = quit): "
        ).strip().lower()

        if again in ("y", "yes"):
            continue
        elif again in ("s", "switch"):
            account_name = pick_account()
            service = authenticate(account_name)
        else:
            print("👋 Done.")
            break

if __name__ == "__main__":
    main()