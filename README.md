# Guide

A Python CLI tool to manage Google Calendar(s). Just like notion-manager, many date formats are supported. The recurrence engine is more powerful. You only need to authenticate your accounts once.

## Setup

### Step 1: Create Google Cloud Project

1. Go to **Google Cloud Console**
2. Click **Select a project** → **NEW PROJECT**
3. Name it (e.g., `"My Calendar Manager"`)
4. Click **CREATE**

---

### Step 2: Enable Google Calendar API

1. In your project, go to **APIs & Services** → **Library**
2. Search for `"Google Calendar API"`
3. Click on it → Click **ENABLE**

---

### Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** → Click **CREATE**
3. Fill in required fields:

   - **App name:** `Calendar Manager`
   - **User support email:** your email
   - **Developer contact:** your email

4. Click **SAVE AND CONTINUE**
5. Skip **Scopes** page (click **SAVE AND CONTINUE**)
6. Skip **Test users** page (click **SAVE AND CONTINUE**)
7. Click **BACK TO DASHBOARD**
8. Leave it in **Testing** mode — this is fine for personal use

---

### Step 4: Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **+ CREATE CREDENTIALS** → **OAuth client ID**
3. Application type: **Desktop app**
4. Name: `Calendar Manager Desktop`
5. Click **CREATE**
6. Click **DOWNLOAD JSON**
7. Rename the file to `credentials.json`

## Using the Script

Create and activate a virtual environment and install dependencies.
```bash
pip install -r requirements.txt
```

Run the application:

```bash
python main.py
```

### Startup Flow

1. **Pick timezone** (once at startup)
2. **Choose account** (or add new one)
3. The examples menu will be offered when creating each event

---

## Use Cases

## 1. Regular Events (with time)

### Single event with specific time

```
Title: Dentist Appointment
Start: tomorrow 2pm
End: tomorrow 3pm
```

### Meeting next week

```
Title: Project Review
Start: next tuesday 10:30 am
End: next tuesday 11:30 am
```

### Using numeric date

```
Title: Birthday Party
Start: 0825 7pm          (August 25 at 7 PM)
End: 0825 11pm
```

---

## 2. All-Day Events (no time)

### Single all-day event

```
Title: Vacation Day
Start: 0701              (July 1, no time = all day)
End: 0701
```

### Multi-day vacation

```
Title: Summer Vacation
Start: 0715
End: 0722                (July 15-22, 8 days)
```

---

## 3. Recurring Events

### A) Simple Repeat (1 additional event, +1 week)

```
Title: Weekly Team Meeting
Start: monday 2pm repeat
End: monday 3pm repeat
```

Creates 2 events: this Monday and next Monday.

---

### B) Count-Based Recurrence

#### Daily for 5 days

```
Title: Meditation
Start: today 7am 5d
End: today 7:30 am 5d
```

#### Weekly for 8 weeks

```
Title: Therapy Session
Start: thursday 4pm 8w
End: thursday 5pm 8w
```

---

### C) Until-Date Recurrence

#### Daily until March 15

```
Title: Morning Workout
Start: today 6am d 0315
End: today 7am d 0315
```

#### Weekly until end of semester

```
Title: Office Hours
Start: friday 2pm w 0515
End: friday 4pm w 0515
```

---

### D) Day Pattern Recurrence (Most Powerful!)

#### Monday / Wednesday / Friday pattern

```
Title: CS 101 Lecture
Start: monday 9am mwf
End: monday 10:30 am mwf
```

Default runs for 4 weeks.

#### Tuesday / Thursday pattern

```
Title: Physics Lab
Start: tuesday 1pm tth
End: tuesday 3pm tth
```

#### Weekdays only

```
Title: Standup Meeting
Start: today 10am mtwrf
End: today 10:15 am mtwrf
```

#### Weekend events

```
Title: Farmers Market
Start: saturday 9am su     (every Sunday)
End: saturday 12pm su
```

---

### E) Combined (Pattern + End Date)

#### MWF until specific date

```
Title: Spanish Class
Start: monday 8am mwf d 0515
End: monday 9am mwf d 0515
```

#### Tue / Thu until end of quarter

```
Title: Seminar
Start: tuesday 3pm tth d 0615
End: tuesday 5pm tth d 0615
```

---

