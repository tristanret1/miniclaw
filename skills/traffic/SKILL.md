---
name: traffic
description: "Real-time traffic conditions via Google Directions API. Use when: user asks about traffic, commute time, road conditions, congestion, or best time to drive. NOT for: general navigation or map directions."
metadata:
  openclaw:
    emoji: "🚗"
    requires:
      bins: ["python3"]
      env: ["GOOGLE_MAPS_API_KEY"]
user-invocable: true
---

# Real-Time Traffic Conditions

Query real-time traffic and congestion between predefined routes using the `exec` tool to run the `traffic.py` script. Requires a Google Maps Directions API key.

## Script Location

The script is at `skills/traffic/traffic.py` relative to the bot's working directory.

## Usage

```bash
# Default: Home → Cypress Mountain
python3 skills/traffic/traffic.py

# Home → Cypress (go skiing)
python3 skills/traffic/traffic.py ski

# Cypress → Home (return)
python3 skills/traffic/traffic.py ski-return

# Both directions
python3 skills/traffic/traffic.py all

# JSON output
python3 skills/traffic/traffic.py --json ski

# Custom origin/destination
python3 skills/traffic/traffic.py --origin "4730 Lougheed Hwy, Burnaby, BC" --dest "Whistler Blackcomb, BC"
```

## Predefined Routes

| Key          | Route                          |
|--------------|--------------------------------|
| `ski`        | Home (4730 Lougheed Hwy) → Cypress Mountain |
| `ski-return` | Cypress Mountain → Home        |

## Output Fields

- **normal_duration** — typical travel time without traffic
- **traffic_duration** — estimated travel time with current traffic
- **delay** — extra time due to congestion
- **congestion_ratio** — traffic/normal ratio (1.0 = no congestion)
- **congestion_level** — 畅通 🟢 / 轻度拥堵 🟡 / 中度拥堵 🟠 / 严重拥堵 🔴
- **routes** — multiple route alternatives, sorted by fastest

## Congestion Classification

| Ratio    | Level          |
|----------|----------------|
| < 1.1    | 畅通 🟢        |
| 1.1–1.3  | 轻度拥堵 🟡    |
| 1.3–1.6  | 中度拥堵 🟠    |
| > 1.6    | 严重拥堵 🔴    |

## When user asks vaguely

- "路况怎么样？" / "Traffic?" → run `ski` (default: home to Cypress)
- "回家堵不堵？" → run `ski-return`
- "去滑雪要多久？" → run `ski`, focus on traffic_duration
- "现在出发合适吗？" → run `ski`, assess congestion level
