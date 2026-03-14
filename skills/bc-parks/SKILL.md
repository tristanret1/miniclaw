---
name: bc-parks
description: "BC Parks campsite availability checker. Use when: user asks about camping availability, campsite booking, BC provincial park reservations, whether parks have open spots. NOT for: general park info, trail conditions, park hours."
metadata:
  openclaw:
    emoji: "🏕️"
    requires:
      bins: ["python3"]
user-invocable: true
---

# BC Parks Campsite Availability

Query BC provincial park campsite availability using the `exec` tool to run the `bc_parks.py` script. No API key needed (uses BC Parks public API).

## Script Location

The script is at `skills/bc-parks/bc_parks.py` relative to the bot's working directory.

## Usage

```bash
# Default: Alice Lake, next 4 weekends
python3 skills/bc-parks/bc_parks.py

# Specific parks
python3 skills/bc-parks/bc_parks.py alice-lake golden-ears

# All built-in parks
python3 skills/bc-parks/bc_parks.py all

# Specific date range
python3 skills/bc-parks/bc_parks.py alice-lake --start 2026-07-04 --end 2026-07-06

# More weekends ahead
python3 skills/bc-parks/bc_parks.py --weekends 8 alice-lake

# JSON output (structured, better for analysis)
python3 skills/bc-parks/bc_parks.py --json alice-lake
```

## Built-in Parks

| Key           | Park                          |
|---------------|-------------------------------|
| `alice-lake`  | Alice Lake Provincial Park    |
| `cultus-lake` | Cultus Lake Provincial Park   |
| `golden-ears` | Golden Ears Provincial Park   |
| `manning`     | E.C. Manning Provincial Park  |

## Output Fields

- **available** — whether any sites are open for the date range
- **total_available** — number of available campsites
- **sites** — list of available sites with resource_id, map_id, remaining_quota, and booking_url
- **booking_url** — direct link to the BC Parks booking page for that specific site/date

## Interpretation Tips

- Each park has multiple zones (map_ids); all are checked in parallel
- `remaining_quota` shows how many spots are left at that site
- Booking URLs link directly to the BC Parks reservation page with dates pre-filled
- Weekend dates are auto-generated (Saturday-Sunday) plus a "tomorrow" check
- Availability changes frequently — results are a snapshot in time

## Known Limitations

- **HTTP 403 on cloud servers**: BC Parks API blocks requests from AWS/GCP/Azure data center IPs (WAF/CDN anti-bot). The script works locally but may return 403 on EC2/cloud instances. If you see 403 errors, inform the user that the BC Parks API is blocking server-side requests and suggest they try running the script locally.
- The `--insecure` flag does NOT fix 403 — it only skips SSL verification, which is a different issue.

## When user asks vaguely

- "Any camping spots?" → run default (alice-lake, next 4 weekends)
- "Can I camp this weekend?" → run all parks, current weekend
- "Is Golden Ears available in July?" → run with `--start` and `--end` for the specific dates
- "Find me a campsite" → run all parks, check next several weekends
