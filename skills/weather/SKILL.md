---
name: weather
description: "Get weather information via wttr.in. Use when: user asks about weather, temperature, forecast."
metadata:
  openclaw:
    emoji: "🌤️"
user-invocable: true
---

# Weather via wttr.in

Use the `exec` tool to query wttr.in for weather data. No API key needed.

## Usage

```bash
# Current weather for a city
curl -s "wttr.in/Tokyo?format=4"

# Detailed forecast (3 days)
curl -s "wttr.in/Tokyo?lang=zh"

# One-line format
curl -s "wttr.in/Tokyo?format=%l:+%c+%t+%h+%w"

# JSON format (for structured data)
curl -s "wttr.in/Tokyo?format=j1"
```

## Format Codes
- `%c` — weather condition emoji
- `%t` — temperature
- `%h` — humidity
- `%w` — wind
- `%l` — location
- `%p` — precipitation

## Tips
- Use `lang=zh` for Chinese output
- Append `?m` to force metric units
- Use city names, airport codes, or coordinates: `wttr.in/48.8566,2.3522`
- For moon phase: `curl -s wttr.in/Moon`
