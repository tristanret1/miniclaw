"""Real-time traffic conditions between predefined routes via Google Directions API."""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

TZ = "America/Vancouver"
API_URL = "https://maps.googleapis.com/maps/api/directions/json"

# Predefined locations
LOCATIONS = {
    "home": {
        "name": "Home (4730 Lougheed Hwy)",
        "address": "4730 Lougheed Highway, Burnaby, BC, Canada",
    },
    "cypress": {
        "name": "Cypress Mountain Resort",
        "address": "Cypress Mountain Resort, West Vancouver, BC, Canada",
    },
}

# Predefined routes
ROUTES = {
    "ski": {
        "name": "Home → Cypress Mountain",
        "origin": "home",
        "destination": "cypress",
    },
    "ski-return": {
        "name": "Cypress Mountain → Home",
        "origin": "cypress",
        "destination": "home",
    },
}


def get_api_key() -> str:
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not key:
        print("Error: GOOGLE_MAPS_API_KEY not set in environment.", file=sys.stderr)
        sys.exit(1)
    return key


def fetch_directions(origin: str, destination: str, api_key: str) -> dict:
    """Fetch directions with real-time traffic."""
    params = {
        "origin": origin,
        "destination": destination,
        "departure_time": "now",
        "traffic_model": "best_guess",
        "alternatives": "true",
        "key": api_key,
    }
    resp = requests.get(API_URL, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data["status"] != "OK":
        raise RuntimeError(f"Directions API error: {data['status']} - {data.get('error_message', '')}")
    return data


def classify_congestion(ratio: float) -> str:
    """Classify congestion based on traffic/normal duration ratio."""
    if ratio < 1.1:
        return "畅通 🟢"
    elif ratio < 1.3:
        return "轻度拥堵 🟡"
    elif ratio < 1.6:
        return "中度拥堵 🟠"
    else:
        return "严重拥堵 🔴"


def format_duration(seconds: int) -> str:
    """Format seconds into human-readable duration."""
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours > 0:
        return f"{hours}h {minutes}min"
    return f"{minutes}min"


def build_report(route_name: str, origin_name: str, dest_name: str, data: dict) -> dict:
    """Build structured report from directions response."""
    now = datetime.now(ZoneInfo(TZ))
    routes = []

    for i, route in enumerate(data["routes"]):
        leg = route["legs"][0]
        normal_sec = leg["duration"]["value"]
        traffic_sec = leg.get("duration_in_traffic", leg["duration"])["value"]
        ratio = traffic_sec / normal_sec if normal_sec > 0 else 1.0

        # Extract step-by-step major roads
        major_steps = []
        for step in leg["steps"]:
            instruction = step["html_instructions"]
            # Strip HTML tags
            import re
            clean = re.sub(r"<[^>]+>", " ", instruction).strip()
            clean = re.sub(r"\s+", " ", clean)
            major_steps.append({
                "instruction": clean,
                "distance": step["distance"]["text"],
                "duration": step["duration"]["text"],
            })

        routes.append({
            "route_index": i,
            "summary": route.get("summary", f"Route {i+1}"),
            "distance": leg["distance"]["text"],
            "normal_duration": format_duration(normal_sec),
            "normal_duration_sec": normal_sec,
            "traffic_duration": format_duration(traffic_sec),
            "traffic_duration_sec": traffic_sec,
            "delay": format_duration(max(0, traffic_sec - normal_sec)),
            "delay_sec": max(0, traffic_sec - normal_sec),
            "congestion_ratio": round(ratio, 2),
            "congestion_level": classify_congestion(ratio),
            "steps": major_steps,
        })

    # Sort by traffic duration (fastest first)
    routes.sort(key=lambda r: r["traffic_duration_sec"])

    return {
        "route_name": route_name,
        "origin": origin_name,
        "destination": dest_name,
        "time": now.strftime("%Y-%m-%d %H:%M %Z"),
        "recommended": routes[0]["summary"] if routes else "N/A",
        "routes": routes,
    }


def format_text(report: dict) -> str:
    """Format report as human-readable text."""
    lines = [
        "=" * 60,
        f"🚗 {report['route_name']}",
        f"📍 {report['origin']} → {report['destination']}",
        f"🕐 {report['time']}",
        f"⭐ 推荐路线: {report['recommended']}",
        "",
    ]

    for r in report["routes"]:
        lines.append(f"--- {r['summary']} ---")
        lines.append(f"  距离: {r['distance']}")
        lines.append(f"  正常耗时: {r['normal_duration']}")
        lines.append(f"  当前耗时: {r['traffic_duration']}")
        lines.append(f"  延迟: +{r['delay']}")
        lines.append(f"  拥堵程度: {r['congestion_level']} (×{r['congestion_ratio']})")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Real-time traffic conditions")
    parser.add_argument("route", nargs="?", default="ski",
                        help="Route key or 'all'. Available: " + ", ".join(ROUTES.keys()))
    parser.add_argument("--origin", help="Custom origin address")
    parser.add_argument("--dest", help="Custom destination address")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    api_key = get_api_key()

    targets = []

    if args.origin and args.dest:
        targets.append(("Custom Route", args.origin, "Custom Origin", args.dest, "Custom Dest"))
    elif args.route == "all":
        for key, route in ROUTES.items():
            o = LOCATIONS[route["origin"]]
            d = LOCATIONS[route["destination"]]
            targets.append((route["name"], o["address"], o["name"], d["address"], d["name"]))
    else:
        key = args.route.lower().strip()
        if key in ROUTES:
            route = ROUTES[key]
            o = LOCATIONS[route["origin"]]
            d = LOCATIONS[route["destination"]]
            targets.append((route["name"], o["address"], o["name"], d["address"], d["name"]))
        else:
            print(f"Unknown route: {key}. Available: {', '.join(ROUTES.keys())}", file=sys.stderr)
            sys.exit(1)

    reports = []
    for route_name, origin_addr, origin_name, dest_addr, dest_name in targets:
        try:
            data = fetch_directions(origin_addr, dest_addr, api_key)
            report = build_report(route_name, origin_name, dest_name, data)
            reports.append(report)
        except Exception as e:
            reports.append({"route_name": route_name, "error": str(e)})

    if args.json:
        print(json.dumps(reports, indent=2, ensure_ascii=False))
    else:
        for report in reports:
            if "error" in report:
                print(f"{'=' * 60}\n{report['route_name']}\nError: {report['error']}\n")
            else:
                print(format_text(report))


if __name__ == "__main__":
    main()
