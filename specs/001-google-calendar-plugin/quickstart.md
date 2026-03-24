# Quickstart: Google Calendar Integration

## Prerequisites

1. A Google Cloud project with Calendar API enabled
2. OAuth 2.0 client credentials (Desktop app type) from Google Cloud Console
3. Two Google Calendar IDs (Life and Work calendars)
4. Existing miniclaw setup (Discord bot running)

## Setup Steps

### 1. Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable the **Google Calendar API**
4. Create OAuth 2.0 credentials:
   - Application type: **Desktop app**
   - Download the client ID and client secret

### 2. Install Dependencies

```bash
pip install google-auth-oauthlib google-api-python-client google-auth
```

Or add to `requirements.txt` and run:
```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Add to `.env`:
```env
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_CALENDAR_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CALENDAR_CLIENT_SECRET=your-client-secret
GOOGLE_CALENDAR_LIFE_ID=your-life-calendar@gmail.com
GOOGLE_CALENDAR_WORK_ID=your-work-calendar@group.calendar.google.com
```

### 4. Run Google OAuth Setup

```bash
python setup.py
```

Select the Google Calendar setup option. A browser window will open for OAuth consent. Grant access to both calendars.

Tokens are saved to `.google_credentials.json` (0o600 permissions).

### 5. Find Your Calendar IDs

- Go to [Google Calendar Settings](https://calendar.google.com/calendar/r/settings)
- Click on each calendar → "Integrate calendar"
- Copy the **Calendar ID** (looks like an email address)

### 6. Verify

Start the bot and ask: "What's on my calendar today?"

The bot should return a merged view of events from both calendars.

## Usage Examples

**View schedule:**
- "What's on my calendar today?"
- "What do I have next week?"
- "Show my work meetings tomorrow"

**Create personal event:**
- "Add dinner with friends Saturday at 7pm"
- "Schedule a dentist appointment next Tuesday at 2pm"

**Create urgent event:**
- "Add urgent: pick up passport tomorrow 5pm"
- "Add an urgent dentist appointment tomorrow at 2pm, remind me 30 minutes before by phone"

**Modify/delete:**
- "Move my dinner to 8pm"
- "Cancel the dentist appointment on Tuesday"

**Daily briefing:**
- "Send me my schedule every morning at 8am"

## Troubleshooting

| Issue | Solution |
| ----- | -------- |
| "Authentication expired" | Re-run `python setup.py` and redo Google OAuth |
| "Calendar not found" | Verify calendar IDs in `.env` match Google Calendar settings |
| Events not showing | Check that the calendar has events in the requested date range |
| Urgent reminder not firing | Verify Twilio credentials are configured for phone/SMS |
