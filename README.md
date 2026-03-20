# FRS Attendance System — Setup Guide

## What this is
A mobile-friendly Face Recognition Attendance system.
Faculty opens the app on Android, scans each student's face, confirms, and attendance is saved.

---

## STEP 1 — Host on Render (Free, works on mobile data)

1. Create a free account at https://github.com and upload this folder as a new repository
2. Go to https://render.com → Sign up free
3. Click "New Web Service" → Connect your GitHub repo
4. Render auto-detects render.yaml and deploys
5. You get a URL like: https://frs-attendance.onrender.com

> Note: Free Render instances sleep after 15 min of inactivity.
> First load may take 30 seconds. Upgrade to paid ($7/mo) to keep it always on.

---

## STEP 2 — Install on Android (PWA)

1. Open Chrome on your Android phone
2. Go to your Render URL
3. Chrome shows "Add to Home Screen" banner → tap it
4. App installs like an APK — fullscreen, no browser bar

---

## STEP 3 — First Time Setup

1. Open the app → tap "Setup faculty account"
2. Enter your name, username, password
3. Login with those credentials

---

## STEP 4 — Register Students

1. Go to Students → Add Student
2. Enter name and roll number
3. Start camera → capture clear face photo
4. Save — student is registered

Do this for all 30-60 students once.

---

## STEP 5 — Daily Attendance

1. Open app on your phone in class
2. Tap "Scan Face & Mark Attendance"
3. Allow location (must be on campus)
4. Point camera at student → tap "Scan Student Face"
5. App shows student name + confirmation
6. Tap ✅ Mark Present
7. Repeat for each student

---

## STEP 6 — View Reports

- Go to Report tab
- See today's present/absent list
- Change date to view past days
- Each student shows attendance % overall

---

## Campus GPS Config

To update campus location, edit these 3 lines in app.py:

```python
CAMPUS_LAT    = 15.8281   # Your campus latitude
CAMPUS_LNG    = 78.0373   # Your campus longitude  
CAMPUS_RADIUS = 500       # Allowed radius in meters
```

Get your exact coordinates: open Google Maps → long press on campus → copy coordinates.

---

## Run Locally (for testing on WiFi)

```
py -3.11 -m pip install -r requirements.txt
py -3.11 app.py
```

Then on phone: http://YOUR_PC_IP:5000
Find your IP: run `ipconfig` → look for IPv4 under WiFi
