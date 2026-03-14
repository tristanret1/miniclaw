"""Ski resort snow forecast via Open-Meteo API (free, no API key needed)."""

import argparse
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

API_URL = "https://api.open-meteo.com/v1/forecast"

# Built-in resorts — users can also pass custom coordinates
RESORTS = {
    "cypress": {
        "name": "Cypress Mountain",
        "latitude": 49.395,
        "longitude": -123.204,
        "timezone": "America/Vancouver",
    },
    "whistler": {
        "name": "Whistler Blackcomb",
        "latitude": 50.116,
        "longitude": -122.957,
        "timezone": "America/Vancouver",
    },
    "grouse": {
        "name": "Grouse Mountain",
        "latitude": 49.380,
        "longitude": -123.082,
        "timezone": "America/Vancouver",
    },
    "seymour": {
        "name": "Mt Seymour",
        "latitude": 49.367,
        "longitude": -122.948,
        "timezone": "America/Vancouver",
    },
    "big-white": {
        "name": "Big White",
        "latitude": 49.725,
        "longitude": -118.933,
        "timezone": "America/Vancouver",
    },
    "sun-peaks": {
        "name": "Sun Peaks",
        "latitude": 50.882,
        "longitude": -119.886,
        "timezone": "America/Vancouver",
    },
    "revelstoke": {
        "name": "Revelstoke Mountain",
        "latitude": 51.029,
        "longitude": -118.164,
        "timezone": "America/Vancouver",
    },
}


def fetch_forecast(latitude: float, longitude: float, timezone: str, days: int = 7) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "forecast_days": days,
        "hourly": ",".join([
            "snowfall",
            "snow_depth",
            "temperature_2m",
            "wind_speed_10m",
            "freezing_level_height",
            "weather_code",
        ]),
        "daily": ",".join([
            "snowfall_sum",
            "temperature_2m_max",
            "temperature_2m_min",
            "weather_code",
        ]),
    }
    resp = requests.get(API_URL, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def to_dt_list(time_strings: list[str], tz_name: str) -> list[datetime]:
    tz = ZoneInfo(tz_name)
    return [datetime.fromisoformat(ts).replace(tzinfo=tz) for ts in time_strings]


def sum_snowfall_next_hours(hourly_times, hourly_snowfall, hours: int, now: datetime) -> float:
    total = 0.0
    end_ts = now.timestamp() + hours * 3600
    for t, snow in zip(hourly_times, hourly_snowfall):
        ts = t.timestamp()
        if now.timestamp() <= ts < end_ts:
            total += snow or 0.0
    return round(total, 1)


def build_report(name: str, data: dict, timezone: str) -> dict:
    """Build a structured report dict for a single resort."""
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)

    hourly = data["hourly"]
    daily = data["daily"]
    hourly_times = to_dt_list(hourly["time"], timezone)

    snow_24h = sum_snowfall_next_hours(hourly_times, hourly["snowfall"], 24, now)
    snow_48h = sum_snowfall_next_hours(hourly_times, hourly["snowfall"], 48, now)
    snow_72h = sum_snowfall_next_hours(hourly_times, hourly["snowfall"], 72, now)

    # Next 12 hourly points
    hourly_detail = []
    for i, t in enumerate(hourly_times):
        if t >= now and len(hourly_detail) < 12:
            hourly_detail.append({
                "time": t.strftime("%Y-%m-%d %H:%M"),
                "snowfall_cm": hourly["snowfall"][i],
                "temp_c": hourly["temperature_2m"][i],
                "wind_kmh": hourly["wind_speed_10m"][i],
                "freezing_level_m": hourly["freezing_level_height"][i],
            })

    # Daily totals
    daily_detail = []
    for i in range(min(7, len(daily["time"]))):
        daily_detail.append({
            "date": daily["time"][i],
            "snowfall_sum_cm": daily["snowfall_sum"][i],
            "temp_min_c": daily["temperature_2m_min"][i],
            "temp_max_c": daily["temperature_2m_max"][i],
        })

    snow_depth = hourly.get("snow_depth", [])
    current_depth = snow_depth[0] if snow_depth else None

    return {
        "resort": name,
        "coordinates": f"{data['latitude']}, {data['longitude']}",
        "time": now.strftime("%Y-%m-%d %H:%M %Z"),
        "snow_next_24h_cm": snow_24h,
        "snow_next_48h_cm": snow_48h,
        "snow_next_72h_cm": snow_72h,
        "current_snow_depth_m": current_depth,
        "hourly_next_12": hourly_detail,
        "daily_forecast": daily_detail,
    }


def format_text(report: dict) -> str:
    """Format report as human-readable text."""
    lines = [
        "=" * 60,
        f"⛷️  {report['resort']}",
        f"Coordinates: {report['coordinates']}",
        f"Time: {report['time']}",
        "",
        f"🌨️  New snow next 24h: {report['snow_next_24h_cm']} cm",
        f"🌨️  New snow next 48h: {report['snow_next_48h_cm']} cm",
        f"🌨️  New snow next 72h: {report['snow_next_72h_cm']} cm",
    ]

    if report["current_snow_depth_m"] is not None:
        lines.append(f"📏 Current snow depth: {report['current_snow_depth_m']} m")

    lines.append("")
    lines.append("Hourly forecast (next 12h):")
    for h in report["hourly_next_12"]:
        lines.append(
            f"  {h['time']} | snow={h['snowfall_cm']}cm "
            f"temp={h['temp_c']}°C wind={h['wind_kmh']}km/h "
            f"freeze={h['freezing_level_m']}m"
        )

    lines.append("")
    lines.append("Daily forecast:")
    for d in report["daily_forecast"]:
        lines.append(
            f"  {d['date']} | snow={d['snowfall_sum_cm']}cm "
            f"temp={d['temp_min_c']}~{d['temp_max_c']}°C"
        )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Ski resort snow forecast")
    parser.add_argument("resorts", nargs="*", default=["cypress", "whistler"],
                        help="Resort keys or 'all'. Available: " + ", ".join(RESORTS.keys()))
    parser.add_argument("--lat", type=float, help="Custom latitude")
    parser.add_argument("--lon", type=float, help="Custom longitude")
    parser.add_argument("--name", default="Custom Location", help="Name for custom location")
    parser.add_argument("--tz", default="America/Vancouver", help="Timezone")
    parser.add_argument("--days", type=int, default=7, help="Forecast days (1-16)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    targets = []

    if args.lat is not None and args.lon is not None:
        targets.append((args.name, args.lat, args.lon, args.tz))
    else:
        resort_keys = list(RESORTS.keys()) if "all" in args.resorts else args.resorts
        for key in resort_keys:
            key_lower = key.lower().strip()
            if key_lower in RESORTS:
                r = RESORTS[key_lower]
                targets.append((r["name"], r["latitude"], r["longitude"], r["timezone"]))
            else:
                print(f"Unknown resort: {key}. Available: {', '.join(RESORTS.keys())}", file=sys.stderr)

    if not targets:
        print("No valid resorts specified.", file=sys.stderr)
        sys.exit(1)

    reports = []
    for name, lat, lon, tz in targets:
        try:
            data = fetch_forecast(lat, lon, tz, args.days)
            report = build_report(name, data, tz)
            reports.append(report)
        except Exception as e:
            reports.append({"resort": name, "error": str(e)})

    if args.json:
        print(json.dumps(reports, indent=2, ensure_ascii=False))
    else:
        for report in reports:
            if "error" in report:
                print(f"{'=' * 60}\n{report['resort']}\nError: {report['error']}\n")
            else:
                print(format_text(report))
                print()


if __name__ == "__main__":
    main()
