"""紫微斗数命盘排盘脚本 — 供 MiniClaw exec tool 调用."""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="紫微斗数排盘")
    parser.add_argument("date", help="日期 YYYY-M-D (如 1990-8-16)")
    parser.add_argument("-t", "--time", required=True, help="时辰 (子/丑/寅/... 或 0-11)")
    parser.add_argument("-g", "--gender", required=True, choices=["男", "女"], help="性别")
    parser.add_argument("--lunar", action="store_true", help="输入为农历日期")
    parser.add_argument("--leap", action="store_true", help="农历闰月")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    try:
        from ziwei.astro import generate_astrolabe
        from ziwei.calendar_utils import time_name_to_index
        from ziwei.formatter import format_astrolabe
    except ImportError:
        print("ERROR: ziwei-cli not installed. Run: pip install ziwei-cli", file=sys.stderr)
        sys.exit(1)

    time_index = time_name_to_index(args.time)
    astrolabe = generate_astrolabe(
        date_str=args.date,
        time_index=time_index,
        gender=args.gender,
        is_lunar=args.lunar,
        is_leap_month=args.leap,
    )

    if args.json:
        print(json.dumps(_astrolabe_to_dict(astrolabe), ensure_ascii=False, indent=2))
    else:
        print(format_astrolabe(astrolabe, use_color=False))


def _astrolabe_to_dict(astrolabe) -> dict:
    """Convert Astrolabe dataclass to a JSON-serializable dict."""
    return {
        "gender": astrolabe.gender,
        "solar_date": astrolabe.solar_date,
        "lunar_date": astrolabe.lunar_date,
        "chinese_date": astrolabe.chinese_date,
        "time_name": astrolabe.time_name,
        "time_range": astrolabe.time_range,
        "zodiac": astrolabe.zodiac,
        "soul_palace": astrolabe.soul_palace,
        "body_palace": astrolabe.body_palace,
        "soul_star": astrolabe.soul_star,
        "body_star": astrolabe.body_star,
        "five_elements_class": astrolabe.five_elements_class,
        "palaces": [
            {
                "index": p.index,
                "name": p.name,
                "heavenly_stem": p.heavenly_stem,
                "earthly_branch": p.earthly_branch,
                "is_body_palace": p.is_body_palace,
                "decadal_range": list(p.decadal_range),
                "decadal_stem": p.decadal_stem,
                "decadal_branch": p.decadal_branch,
                "major_stars": [
                    {"name": s.name, "brightness": s.brightness, "mutagen": s.mutagen}
                    for s in p.major_stars
                ],
                "minor_stars": [
                    {"name": s.name, "brightness": s.brightness, "mutagen": s.mutagen}
                    for s in p.minor_stars
                ],
                "adjective_stars": [{"name": s.name} for s in p.adjective_stars],
                "changsheng12": p.changsheng12,
                "boshi12": p.boshi12,
                "jiangqian12": p.jiangqian12,
                "suiqian12": p.suiqian12,
            }
            for p in astrolabe.palaces
        ],
    }


if __name__ == "__main__":
    main()
