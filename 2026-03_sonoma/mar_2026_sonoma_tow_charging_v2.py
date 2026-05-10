from math import floor

import numpy as np
import pandas as pd

pd.set_option("display.max_rows", None)  # Show all rows
pd.set_option("display.max_columns", None)  # Show all columns
pd.set_option("display.expand_frame_repr", False)  # Prevent wrapping across lines
pd.set_option("display.max_colwidth", None)  # Show full column content

# 62 kWh usable pack
# 0–70% @ 70 kW
# 70–92% @ 50 kW
# 92–93% @ 30 kW
# 93–94.4% @ 25 kW

# make 20% the minimum
charge_data: list[list[float | int] | list[float]] = [
    # [percent, minutes]
    # [0, 0.0],
    # [5, 2.7],
    # [10, 5.3],
    # [15, 8.0],
    [20, 10.6 - 10.6],
    [25, 13.3 - 10.6],
    [30, 16.0 - 10.6],
    [35, 18.6 - 10.6],
    [40, 21.3 - 10.6],
    [45, 24.0 - 10.6],
    [50, 26.6 - 10.6],
    [55, 29.3 - 10.6],
    [60, 32.0 - 10.6],
    [65, 34.6 - 10.6],
    [70, 37.2 - 10.6],
    [75, 41.0 - 10.6],
    [80, 44.7 - 10.6],
    [85, 48.5 - 10.6],
    [90, 52.2 - 10.6],
    [92, 53.5 - 10.6],
    [93, 54.7 - 10.6],
    [94, 55.6 - 10.6],
    [94.4, 56.8 - 10.6],
]


lap_data = [
    # minutes, percent
    [145.0 / 60, 3.0],
    [150.0 / 60, 2.5],
    [155.0 / 60, 2.1],
    # [160.0 / 60, 1.8],
    # [170.0 / 60, 1.5],
    # [180.0 / 60, 1.3],
    # [190.0 / 60, 1.1],
]


hookup_time = 5  # minutes to hook up to the charger
charge_delay_time = 15  # minutes for charging delays (traffic, lights, etc.)


def try_scenario(race_minutes, lap_time, lap_pct, charge_time, charge_pct):
    curr_pct = 96.3
    total_laps = 0
    elapsed_time = 0
    df = pd.DataFrame(
        [("Start Race", elapsed_time, curr_pct, total_laps)],
        columns=["Event", "Duration (min)", "End Battery (%)", "Laps"],
    )

    while elapsed_time < race_minutes:
        # Check if there's enough time for another charge cycle after this stint.
        # A charge cycle costs: 5 min hookup + charge_time + 15 min delays + at least 1 lap.
        charge_cycle_time = hookup_time + charge_time + charge_delay_time + lap_time

        # Drive down to 20% early/mid race, but 5% on the final stint
        exit_pct = 20
        pct_used_at_20 = curr_pct - 20
        laps_at_20 = floor(pct_used_at_20 / lap_pct)
        time_at_20 = laps_at_20 * lap_time
        time_remaining_after = race_minutes - (elapsed_time + time_at_20)
        if time_remaining_after < charge_cycle_time:
            exit_pct = 5  # final stint — drain lower

        pct_used = curr_pct - exit_pct
        max_laps = floor(pct_used / lap_pct)
        max_time = max_laps * lap_time
        if elapsed_time + max_time > race_minutes:
            max_laps = floor((race_minutes - elapsed_time) / lap_time)
            max_time = max_laps * lap_time

        curr_pct -= max_laps * lap_pct
        elapsed_time += max_time
        total_laps += max_laps
        df.loc[len(df)] = ["End Stint", round(elapsed_time, 1), curr_pct, total_laps]

        if elapsed_time >= race_minutes:
            break

        elapsed_time += hookup_time
        df.loc[len(df)] = [
            "Start Charging",
            round(elapsed_time, 1),
            curr_pct,
            total_laps,
        ]

        if elapsed_time >= race_minutes:
            break

        elapsed_time += charge_time  # Charging time
        curr_pct = charge_pct
        df.loc[len(df)] = ["End Charging", round(elapsed_time, 1), curr_pct, total_laps]

        if elapsed_time >= race_minutes:
            break

        df.loc[len(df)] = ["Buffer", "", "", ""]

        elapsed_time += charge_delay_time
        df.loc[len(df)] = ["Start Stint", round(elapsed_time, 1), curr_pct, total_laps]

    return {"curr_laps": total_laps, "curr_time": elapsed_time, "df": df}


def run_race_simulation(race_minutes, race_name, start_hour, track_miles):
    results = []

    for charge_pct, charge_time in charge_data:
        for lap_time_min, lap_pct in lap_data:
            result = try_scenario(
                race_minutes, lap_time_min, lap_pct, charge_time, charge_pct
            )
            results.append(
                {
                    "charge_pct": charge_pct,
                    "charge_time": charge_time,
                    "lap_time_min": round(lap_time_min, 2),
                    "lap_pct": lap_pct,
                    "curr_laps": result["curr_laps"],
                    "curr_time": result["curr_time"],
                    "df": result["df"],
                }
            )

    df_results = pd.DataFrame(results).sort_values(by="curr_laps", ascending=False)
    top_results = df_results.head(2)

    print(f"\n========== {race_name} Plan ==========")
    for idx, row in top_results.iterrows():
        print(f"\n===== Scenario {idx + 1} =====")
        print(f"Charge %: {row['charge_pct']} | Charge Time: {row['charge_time']} min")
        lap_mm = int(row["lap_time_min"])
        lap_ss = int(round((row["lap_time_min"] - lap_mm) * 60))
        print(
            f"Lap Time: {lap_mm}:{lap_ss:02d} | Battery Used per Lap: {row['lap_pct']}%"
        )
        total_h = int(row["curr_time"] // 60)
        total_m = int(row["curr_time"] % 60)
        print(
            f"Total Laps Completed: {row['curr_laps']} | Total Time: {total_h}h {total_m}m"
        )
        print("\nEvent Log:")
        log_df = row["df"].copy()
        log_df["Time"] = log_df["Duration (min)"].apply(
            lambda m: (
                (
                    lambda h, mm: f"{h if h <= 12 else h - 12}:{mm:02d} {'AM' if h < 12 else 'PM'}"
                )(int((start_hour * 60 + m) // 60), int((start_hour * 60 + m) % 60))
                if m != ""
                else ""
            )
        )
        log_df["Miles"] = log_df["Laps"].apply(
            lambda l: int(round(l * track_miles)) if l != "" else ""
        )
        log_df["End Battery (%)"] = log_df["End Battery (%)"].apply(
            lambda b: int(round(b)) if b != "" else ""
        )
        log_df = log_df[["Event", "Time", "End Battery (%)", "Laps", "Miles"]]
        # Compute column widths for aligned output
        col_widths = {}
        for col in log_df.columns:
            max_val_width = log_df[col].astype(str).str.len().max()
            col_widths[col] = max(len(col), max_val_width)
        # Print header
        header_parts = [f"{col:>{col_widths[col]}}" for col in log_df.columns]
        print(", ".join(header_parts))
        # Print rows
        for _, r in log_df.iterrows():
            row_parts = [f"{str(r[col]):>{col_widths[col]}}" for col in log_df.columns]
            print(", ".join(row_parts))
        print("=" * 40)


track_delay_buffer = 30  # 30 mins for yellow/black/red flags
track_miles = 2.51

race_duration = 7.0 * 60 - track_delay_buffer  # day 1 is 8 hours.
run_race_simulation(race_duration, "Saturday race", start_hour=10, track_miles=track_miles)

race_duration = 7.0 * 60 - track_delay_buffer  # day 2 is 6.5 hours.
run_race_simulation(race_duration, "Sunday race", start_hour=9, track_miles=track_miles)
