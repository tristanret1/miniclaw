---
name: snow-forecast
description: "Ski resort snow forecast via Open-Meteo API. Use when: user asks about snow conditions, ski resort weather, powder days, snowfall forecast. NOT for: general weather."
metadata:
  openclaw:
    emoji: "🎿"
    requires:
      bins: ["python3"]
user-invocable: true
---

# Ski Resort Snow Forecast

Query snow forecasts for BC ski resorts using the `exec` tool to run the `snow_forecast.py` script. No API key needed (uses free Open-Meteo API).

## Script Location

The script is at `skills/snow-forecast/snow_forecast.py` relative to the bot's working directory.

## Usage

```bash
# Default: Cypress + Whistler
python3 skills/snow-forecast/snow_forecast.py

# Specific resorts
python3 skills/snow-forecast/snow_forecast.py cypress whistler grouse

# All built-in resorts
python3 skills/snow-forecast/snow_forecast.py all

# JSON output (structured, better for analysis)
python3 skills/snow-forecast/snow_forecast.py --json cypress

# Custom coordinates (any mountain)
python3 skills/snow-forecast/snow_forecast.py --lat 46.938 --lon 11.461 --name "Stubai Glacier" --tz "Europe/Vienna"
```

## Built-in Resorts

| Key          | Resort              |
|--------------|---------------------|
| `cypress`    | Cypress Mountain    |
| `whistler`   | Whistler Blackcomb  |
| `grouse`     | Grouse Mountain     |
| `seymour`    | Mt Seymour          |
| `big-white`  | Big White           |
| `sun-peaks`  | Sun Peaks           |
| `revelstoke` | Revelstoke Mountain |

## Output Fields

- **snow_next_24h/48h/72h_cm** — cumulative new snowfall forecast
- **current_snow_depth_m** — modeled current snow depth
- **hourly_next_12** — hour-by-hour: snowfall, temperature, wind, freezing level
- **daily_forecast** — day-by-day: total snowfall, min/max temperature

## Interpretation Tips

- **Powder day**: 15+ cm in 24h with temps below -5°C
- **Freezing level**: if above resort elevation, expect rain instead of snow
- **Wind**: 50+ km/h typically means exposed lifts may close
- Snow depth is modeled, not measured — treat as estimate

## When user asks vaguely

- "How's the snow?" → run default (cypress + whistler)
- "Should I go skiing this weekend?" → run all resorts, compare 48h-72h snowfall
- "Is there powder?" → focus on 24h snowfall + temperature
