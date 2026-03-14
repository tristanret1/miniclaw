"""BC Parks campsite availability checker via BC Parks API (no API key needed)."""

import argparse
import asyncio
import datetime
import json
import sys
import uuid
from typing import Any

import ssl

import aiohttp

API_BASE = "https://camping.bcparks.ca/api/availability/map"

API_PARAMS = {
    "bookingCategoryId": 0,
    "equipmentCategoryId": -32768,
    "subEquipmentCategoryId": -32768,
    "filterData": "[]",
    "boatLength": 0,
    "boatDraft": 0,
    "boatWidth": 0,
    "peopleCapacityCategoryCounts": "[]",
    "numEquipment": 0,
    "isReserving": "true",
    "getDailyAvailability": "false",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://camping.bcparks.ca/",
    "Origin": "https://camping.bcparks.ca",
}

# Built-in parks — users can also pass custom resource/map IDs
PARKS: dict[str, dict[str, Any]] = {
    "alice-lake": {
        "name": "Alice Lake Provincial Park",
        "resource_id": "-2147483647",
        "map_ids": ["-2147483647", "-2147483646", "-2147483645", "-2147483644"],
    },
    "cultus-lake": {
        "name": "Cultus Lake Provincial Park",
        "resource_id": "-2147483623",
        "map_ids": ["-2147483610", "-2147483606", "-2147483608", "-2147483609"],
    },
    "golden-ears": {
        "name": "Golden Ears Provincial Park",
        "resource_id": "-2147483606",
        "map_ids": ["-2147483574", "-2147483575", "-2147483573", "-2147483572"],
    },
    "manning": {
        "name": "E.C. Manning Provincial Park",
        "resource_id": "-2147482026",
        "map_ids": ["-2147483598"],
    },
}

BOOKING_URL_BASE = "https://camping.bcparks.ca/create-booking/results?"


def _session_ids() -> dict[str, str]:
    return {
        "cartUid": str(uuid.uuid4()),
        "cartTransactionUid": str(uuid.uuid4()),
        "bookingUid": str(uuid.uuid4()),
        "groupHoldUid": "",
        "seed": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
    }


def _booking_url(resource_id: str, map_id: str, start: str, end: str) -> str:
    return (
        f"{BOOKING_URL_BASE}resourceLocationId={resource_id}"
        f"&mapId={map_id}&startDate={start}&endDate={end}"
        f"&equipmentId=-32768&subEquipmentId=-32768"
    )


def _parse_availability(data: dict) -> list[dict]:
    """Extract available sites from API response."""
    sites: list[dict] = []
    resource_avail = data.get("resourceAvailabilities", {})
    for resource_id, avail_list in resource_avail.items():
        for entry in avail_list:
            if entry.get("availability") == 0:
                sites.append({
                    "resource_id": resource_id,
                    "remaining_quota": entry.get("remainingQuota"),
                })
                break
    return sites


async def check_map(
    session: aiohttp.ClientSession,
    map_id: str,
    start_date: str,
    end_date: str,
) -> dict:
    """Query a single map_id for availability."""
    params = {
        "mapId": map_id,
        "startDate": start_date,
        "endDate": end_date,
        **API_PARAMS,
        **_session_ids(),
    }
    try:
        async with session.get(API_BASE, params=params) as resp:
            if resp.status != 200:
                return {"map_id": map_id, "error": f"HTTP {resp.status}", "sites": []}
            data = await resp.json()
            return {"map_id": map_id, "error": None, "sites": _parse_availability(data)}
    except Exception as e:
        return {"map_id": map_id, "error": str(e), "sites": []}


async def check_park(
    session: aiohttp.ClientSession,
    park_key: str,
    park_info: dict,
    start_date: str,
    end_date: str,
) -> dict:
    """Check all map_ids for a park and merge results."""
    tasks = [
        check_map(session, mid, start_date, end_date)
        for mid in park_info["map_ids"]
    ]
    results = await asyncio.gather(*tasks)

    all_sites: list[dict] = []
    errors: list[str] = []
    for r in results:
        if r["error"]:
            errors.append(f"map {r['map_id']}: {r['error']}")
        for site in r["sites"]:
            site["map_id"] = r["map_id"]
            site["booking_url"] = _booking_url(
                park_info["resource_id"], r["map_id"], start_date, end_date
            )
            all_sites.append(site)

    return {
        "park": park_info["name"],
        "key": park_key,
        "start_date": start_date,
        "end_date": end_date,
        "available": len(all_sites) > 0,
        "total_available": len(all_sites),
        "maps_checked": len(park_info["map_ids"]),
        "sites": all_sites,
        "errors": errors,
    }


def _next_weekends(weeks: int = 4) -> list[tuple[str, str, str]]:
    """Generate upcoming weekend date ranges (Sat-Sun)."""
    today = datetime.date.today()
    days_until_sat = (5 - today.weekday()) % 7
    if days_until_sat == 0 and today.weekday() != 5:
        days_until_sat = 7

    weekends = []
    # Include tomorrow as "today" check
    tomorrow = today + datetime.timedelta(days=1)
    day_after = today + datetime.timedelta(days=2)
    weekends.append((
        tomorrow.isoformat(),
        day_after.isoformat(),
        f"tomorrow ({tomorrow.strftime('%m/%d')})",
    ))

    next_sat = today + datetime.timedelta(days=days_until_sat)
    for i in range(weeks):
        sat = next_sat + datetime.timedelta(weeks=i)
        sun = sat + datetime.timedelta(days=1)
        label = f"weekend ({sat.strftime('%m/%d')}-{sun.strftime('%m/%d')})"
        weekends.append((sat.isoformat(), sun.isoformat(), label))
    return weekends


def format_text(results: list[dict]) -> str:
    lines: list[str] = []
    for r in results:
        lines.append("=" * 60)
        lines.append(f"  {r['park']}")
        lines.append(f"  {r['start_date']} ~ {r['end_date']}")
        if r["available"]:
            lines.append(f"  AVAILABLE — {r['total_available']} site(s) found")
            for s in r["sites"][:10]:
                quota = f" (quota: {s['remaining_quota']})" if s["remaining_quota"] is not None else ""
                lines.append(f"    site {s['resource_id']} [map:{s['map_id']}]{quota}")
                lines.append(f"      {s['booking_url']}")
            if len(r["sites"]) > 10:
                lines.append(f"    ... and {len(r['sites']) - 10} more")
        else:
            lines.append("  NO availability")
        if r["errors"]:
            lines.append(f"  errors: {'; '.join(r['errors'])}")
        lines.append("")
    return "\n".join(lines)


async def run(
    park_keys: list[str],
    start_date: str | None,
    end_date: str | None,
    weekends: int,
    as_json: bool,
    insecure: bool = False,
) -> None:
    timeout = aiohttp.ClientTimeout(total=30)
    connector = None
    if insecure:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout, connector=connector) as session:
        all_results: list[dict] = []

        # Determine date ranges
        if start_date and end_date:
            date_ranges = [(start_date, end_date, f"{start_date} ~ {end_date}")]
        else:
            date_ranges = _next_weekends(weekends)

        # Determine parks
        targets: list[tuple[str, dict]] = []
        for key in park_keys:
            k = key.lower().strip()
            if k in PARKS:
                targets.append((k, PARKS[k]))
            else:
                print(f"Unknown park: {key}. Available: {', '.join(PARKS.keys())}", file=sys.stderr)

        if not targets:
            print("No valid parks specified.", file=sys.stderr)
            sys.exit(1)

        tasks = []
        for s, e, _label in date_ranges:
            for pk, pi in targets:
                tasks.append(check_park(session, pk, pi, s, e))

        results = await asyncio.gather(*tasks)
        all_results.extend(results)

        if as_json:
            print(json.dumps(all_results, indent=2, ensure_ascii=False))
        else:
            print(format_text(all_results))


def main() -> None:
    parser = argparse.ArgumentParser(description="BC Parks campsite availability checker")
    parser.add_argument(
        "parks", nargs="*", default=["alice-lake"],
        help="Park keys or 'all'. Available: " + ", ".join(PARKS.keys()),
    )
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    parser.add_argument("--weekends", type=int, default=4, help="Number of weekends to check (default: 4)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--insecure", action="store_true", help="Skip SSL verification")
    args = parser.parse_args()

    park_keys = list(PARKS.keys()) if "all" in args.parks else args.parks

    if bool(args.start) != bool(args.end):
        print("Both --start and --end are required when specifying dates.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run(park_keys, args.start, args.end, args.weekends, args.json, args.insecure))


if __name__ == "__main__":
    main()
