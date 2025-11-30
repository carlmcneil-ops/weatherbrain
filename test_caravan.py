"""
Very simple smoke test for caravan_engine.
"""

from caravan_regions import CARAVAN_REGIONS
from caravan_engine import score_caravan_day, find_best_caravan_windows


def main():
    print("=== Caravan engine smoke test ===")

    # Use the first 2 regions for testing
    regions = CARAVAN_REGIONS[:2]

    # Fake 3 days of OK-ish weather for each region
    forecast_by_region = {}
    for r in regions:
        rid = r["id"]
        forecast_by_region[rid] = [
            {
                "date": "2025-12-01",
                "tow_wind": 15,
                "tow_gust": 30,
                "camp_wind": 10,
                "camp_rain": 0.5,
                "camp_rain_prev48": 2,
            },
            {
                "date": "2025-12-02",
                "tow_wind": 18,
                "tow_gust": 35,
                "camp_wind": 12,
                "camp_rain": 2,
                "camp_rain_prev48": 5,
            },
            {
                "date": "2025-12-03",
                "tow_wind": 40,   # deliberately a bit rough
                "tow_gust": 60,
                "camp_wind": 25,
                "camp_rain": 10,
                "camp_rain_prev48": 30,
            },
        ]

    # Print per-day scores
    for r in regions:
        rid = r["id"]
        print(f"\n--- {r['name']} ---")
        for day in forecast_by_region[rid]:
            ds = score_caravan_day(r, day)
            print(
                f"{ds.date}: score={ds.score:.1f}, tow_ok={ds.tow_ok}, "
                f"camp_ok={ds.camp_ok}"
            )

    # Now test window finder (min 2 nights)
    windows = find_best_caravan_windows(
        regions, forecast_by_region, min_nights=2
    )
    print("\n=== Windows detected ===")
    if not windows:
        print("No suitable windows in this dummy data.")
    else:
        for w in windows:
            print(
                f"{w['region_name']}: {w['start_date']} → {w['end_date']} "
                f"({w['nights']} nights, avg_score={w['avg_score']:.1f})"
            )


if __name__ == "__main__":
    main()