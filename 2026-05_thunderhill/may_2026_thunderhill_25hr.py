from math import floor

import pandas as pd

pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)
pd.set_option("display.expand_frame_repr", False)
pd.set_option("display.max_colwidth", None)

# 62 kWh usable pack
# 0–70% @ 70 kW
# 70–92% @ 50 kW
# 92–93% @ 30 kW
# 93–94.4% @ 25 kW

# Charge curve starting from 10% (subtract 5.3 min baseline)
charge_data: list[list[float]] = [
    [10, 0.0],
    [15, 8.0 - 5.3],
    [20, 10.6 - 5.3],
    [25, 13.3 - 5.3],
    [30, 16.0 - 5.3],
    [35, 18.6 - 5.3],
    [40, 21.3 - 5.3],
    [45, 24.0 - 5.3],
    [50, 26.6 - 5.3],
    [55, 29.3 - 5.3],
    [60, 32.0 - 5.3],
    [65, 34.6 - 5.3],
    [70, 37.2 - 5.3],
    [75, 41.0 - 5.3],
    [80, 44.7 - 5.3],
    [85, 48.5 - 5.3],
    [90, 52.2 - 5.3],
    [92, 53.5 - 5.3],
    [93, 54.7 - 5.3],
    [94, 55.6 - 5.3],
    [94.4, 56.8 - 5.3],
]

# Thunderhill 3-mile layout
# [lap_time_seconds, battery_%_per_lap]
# Derived from 2025 Thunderhill 25hr race data
lap_data = [
    [150, 3.4],  # 2:30
    [160, 2.9],  # 2:40
    [170, 2.5],  # 2:50
    [180, 2.2],  # 3:00
    [190, 1.9],  # 3:10
    [200, 1.7],  # 3:20
    [210, 1.5],  # 3:30
]

hookup_time = 5  # minutes to hook up to the charger
charge_delay_time = 20  # minutes buffer after charging
driver_swap_time = 5  # minutes for mid-battery driver change
track_miles = 3.0

# --- Driver definitions ---

drivers = {
    "Alexey": {"lap_time": 160, "pct_per_lap": 2.8, "battery_mode": "full"},
    "Yezhi": {"lap_time": 160, "pct_per_lap": 2.8, "battery_mode": "full"},
    "Roman": {"lap_time": 170, "pct_per_lap": 2.2, "battery_mode": "full"},
    "Forrest": {"lap_time": 160, "pct_per_lap": 2.2, "battery_mode": "half"},
    "Xiaoyu": {"lap_time": 170, "pct_per_lap": 2.2, "battery_mode": "half"},
    "Amethyst": {"lap_time": 160, "pct_per_lap": 2.1, "battery_mode": "full"},
}

race_start_hour = 11
race_minutes = 25 * 60

# Crew members: 2 people must supervise charging.
# Neither can be the driver before or after the charge.
# Blocks with Alexey get Luns, others get Jen.
block_crew = {
    0: "Luns",     # Block 1: Alexey, Yezhi, Roman
    1: "Jen",      # Block 2: Forrest, Xiaoyu, Amethyst
    2: "Luns",     # Block 3: Alexey, Yezhi, Roman
}

blocks = [
    (0, 4, ["Alexey", "Yezhi", "Roman"]),
    (4, 16, ["Forrest", "Xiaoyu", "Amethyst"]),
    (16, 25, ["Alexey", "Yezhi", "Roman"]),
]

def get_block_for_time(elapsed: float) -> int:
    for i, (start_h, end_h, _) in enumerate(blocks):
        if start_h * 60 <= elapsed < end_h * 60:
            return i
    return len(blocks) - 1

def future_opportunities(person: str, stints: list[dict], current_idx: int) -> int:
    """Count how many future charges this person could be eligible for."""
    count = 0
    for j in range(current_idx + 1, len(stints)):
        s2 = stints[j]
        if s2["charge_start_elapsed"] is None:
            continue
        prev2 = stints[j - 1]["driver"] if j > 0 else None
        next2 = s2["driver"]
        if person != next2 and person != prev2:
            # Check person is in the right block
            for bi2, (_, _, bd2) in enumerate(blocks):
                if next2 in bd2:
                    if person in bd2 or person == block_crew[bi2]:
                        count += 1
                    break
    return count


def assign_charge_crews(stints: list[dict]) -> None:
    """Assign charge crews to all stints, balancing duties across people."""
    charge_counts: dict[str, int] = {}
    for s in stints:
        if s["charge_start_elapsed"] is None:
            continue

        # Find prev driver
        idx = stints.index(s)
        prev_driver = stints[idx - 1]["driver"] if idx > 0 else None
        next_driver = s["driver"]

        # Find block for next driver
        bi = None
        for i, (_, _, bd) in enumerate(blocks):
            if next_driver in bd:
                bi = i
                break
        if bi is None:
            bi = 0
        _, _, block_drivers = blocks[bi]
        crew = block_crew[bi]

        excluded = {next_driver}
        if prev_driver:
            excluded.add(prev_driver)
        available_drivers = [p for p in block_drivers if p not in excluded]

        # Pick the available driver with fewest charge duties so far.
        # Break ties by fewest future charge opportunities (prefer those who
        # are harder to schedule).
        if available_drivers:
            available_drivers.sort(key=lambda p: (
                charge_counts.get(p, 0),
                future_opportunities(p, stints, idx),
            ))
            picked = available_drivers[0]
        else:
            picked = crew
        s["charge_crew"] = [picked, crew]
        charge_counts[picked] = charge_counts.get(picked, 0) + 1
        charge_counts[crew] = charge_counts.get(crew, 0) + 1

# --- Stint sequence ---
# Each entry: (driver_name, charge_target_pct or None for no charge first)
# None means "drive on whatever battery is left" (for shared-battery stints)
# "full" means charge to the full_charge_target (determined by optimizer)
# "half" means charge to 50%
# A number means charge to exactly that %

# Block 1 (Sat 11am-3pm): Alexey burns starting battery, charge, Yezhi+Roman share
# Block 2 (Sat 3pm-Sun 3am): Forrest(half), Xiaoyu(half), Amethyst(full), repeat
# Block 3 (Sun 3am-12pm): Alexey(full), Yezhi(full), Roman(full)

stint_sequence = [
    # Block 1 (Sat 11am-3pm, 4hr): Alexey burns start battery, charge, Yezhi+Roman share
    ("Alexey", None, 4 * 60),      # drive starting 96.3%, block ends at 4h
    ("Yezhi", "full", 4 * 60),     # charge to full, Yezhi drives first half
    ("Roman", None, 4 * 60),       # Roman drives rest (no charge, shared battery)
    # Block 2 (Sat 3pm-Sun 3am, 12hr): Xiaoyu+Forrest share a battery, Amethyst full
    ("Xiaoyu", "full", 16 * 60),    # charge full, Xiaoyu drives first half
    ("Forrest", None, 16 * 60),     # Forrest drives second half (shared battery)
    ("Amethyst", "full", 16 * 60),
    ("Xiaoyu", "full", 16 * 60),
    ("Forrest", None, 16 * 60),
    ("Amethyst", "full", 16 * 60),
    ("Xiaoyu", "full", 16 * 60),
    ("Forrest", None, 16 * 60),
    ("Amethyst", "full", 16 * 60),
    ("Xiaoyu", "full", 16 * 60),
    ("Forrest", None, 16 * 60),
    ("Amethyst", "full", 16 * 60),
    # Block 3 (Sun 3am-12pm, 9hr): Alexey, Yezhi, Roman
    ("Alexey", "full", 25 * 60),
    ("Yezhi", "full", 25 * 60),
    ("Roman", "full", 25 * 60),
    ("Alexey", "full", 25 * 60),
    ("Yezhi", "full", 25 * 60),
    ("Roman", "full", 25 * 60),
]


def charge_time_for_pct(target_pct: float) -> float:
    """Minutes to charge from 10% to target_pct."""
    if target_pct <= 10:
        return 0.0
    for i in range(len(charge_data) - 1):
        p0, t0 = charge_data[i]
        p1, t1 = charge_data[i + 1]
        if p0 <= target_pct <= p1:
            frac = (target_pct - p0) / (p1 - p0)
            return t0 + frac * (t1 - t0)
    return charge_data[-1][1]


def charge_time_between(from_pct: float, to_pct: float) -> float:
    if to_pct <= from_pct:
        return 0.0
    return charge_time_for_pct(to_pct) - charge_time_for_pct(from_pct)


def format_clock(elapsed_min: float) -> str:
    total_min = race_start_hour * 60 + elapsed_min
    h = int(total_min // 60) % 24
    m = int(total_min % 60)
    ampm = "AM" if h < 12 else "PM"
    h12 = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
    return f"{h12}:{m:02d} {ampm}"


def build_schedule(full_charge_target: float) -> list[dict]:
    half_charge_target = 50.0
    curr_pct = 96.3
    elapsed = 0.0
    total_laps = 0
    stints = []

    for i, (driver_name, charge_mode, block_deadline) in enumerate(stint_sequence):
        if elapsed >= race_minutes:
            break

        d = drivers[driver_name]
        lap_time_min = d["lap_time"] / 60.0
        lap_pct = d["pct_per_lap"]
        deadline = min(block_deadline, race_minutes)

        # --- Determine charge target ---
        if charge_mode == "full":
            charge_target = full_charge_target
        elif charge_mode == "half":
            charge_target = half_charge_target
        elif charge_mode is None:
            charge_target = None
        else:
            charge_target = float(charge_mode)

        # --- Charge phase ---
        charge_start_elapsed = None
        charge_end_elapsed = None
        charge_start_pct = curr_pct

        # Mid-battery driver swap (no charge, just swap drivers)
        if charge_target is None and len(stints) > 0:
            elapsed += driver_swap_time

        if charge_target is not None and curr_pct < charge_target:
            charge_min = charge_time_between(curr_pct, charge_target)
            total_pit = hookup_time + charge_min + charge_delay_time

            if elapsed + total_pit + lap_time_min > deadline:
                # Can't fit charge + 1 lap before block deadline; skip this stint
                continue

            elapsed += hookup_time
            charge_start_elapsed = elapsed
            elapsed += charge_min
            curr_pct = charge_target
            charge_end_elapsed = elapsed
            elapsed += charge_delay_time
            buffer_end_elapsed = elapsed

            if elapsed >= deadline:
                continue

        # --- Drive phase ---
        # Look ahead: is the next stint a shared-battery stint (charge_mode is None)?
        next_is_shared = (i + 1 < len(stint_sequence) and stint_sequence[i + 1][1] is None)

        exit_pct = 10.0
        if next_is_shared:
            # Leave enough battery for the next driver to get a decent stint.
            # Split: this driver uses half the available range, next gets the rest.
            midpoint = (curr_pct + 10.0) / 2
            exit_pct = max(midpoint, 10.0)

        # Check if this could be the final stint of the race
        pct_avail_10 = curr_pct - 10.0
        laps_if_10 = floor(pct_avail_10 / lap_pct) if pct_avail_10 > 0 else 0
        drive_time_10 = laps_if_10 * lap_time_min
        time_after = race_minutes - (elapsed + drive_time_10)
        min_next_cycle = hookup_time + charge_time_between(10, half_charge_target) + charge_delay_time + lap_time_min
        if time_after < min_next_cycle:
            exit_pct = 5.0

        pct_available = curr_pct - exit_pct
        if pct_available <= 0:
            continue

        max_laps_battery = floor(pct_available / lap_pct)
        time_left = deadline - elapsed
        max_laps_time = floor(time_left / lap_time_min) if time_left > 0 else 0

        stint_laps = min(max_laps_battery, max_laps_time)
        if stint_laps <= 0:
            continue

        stint_time = stint_laps * lap_time_min
        stint_start_pct = curr_pct
        curr_pct -= stint_laps * lap_pct
        drive_start = elapsed
        elapsed += stint_time
        total_laps += stint_laps

        stints.append({
            "driver": driver_name,
            "charge_start_pct": charge_start_pct,
            "charge_target_pct": charge_target if charge_start_elapsed else None,
            "charge_start_elapsed": charge_start_elapsed,
            "charge_end_elapsed": charge_end_elapsed,
            "buffer_end_elapsed": buffer_end_elapsed if charge_start_elapsed else None,
            "charge_min": (charge_end_elapsed - charge_start_elapsed) if charge_start_elapsed else 0,
            "drive_start": drive_start,
            "drive_end": elapsed,
            "start_pct": stint_start_pct,
            "end_pct": curr_pct,
            "laps": stint_laps,
            "total_laps": total_laps,
            "charge_crew": None,
        })

    assign_charge_crews(stints)
    return stints


def find_optimal_charge_level() -> float:
    best_laps = 0
    best_pct = 80.0
    for charge_pct, _ in charge_data:
        if charge_pct < 50:
            continue
        stints = build_schedule(charge_pct)
        total = stints[-1]["total_laps"] if stints else 0
        if total > best_laps:
            best_laps = total
            best_pct = charge_pct
    return best_pct


def print_schedule(stints: list[dict], full_charge_target: float):
    print(f"\n{'='*80}")
    print(f"  THUNDERHILL 25HR RACE PLAN  |  Full charge target: {full_charge_target}%")
    print(f"{'='*80}\n")

    headers = ["Event", "Clock", "Battery", "Laps", "Miles", "Driver", "Charge Crew"]
    col_w = [16, 10, 8, 6, 6, 10, 20]
    header_str = "  ".join(f"{h:>{w}}" for h, w in zip(headers, col_w))
    print(header_str)
    print("-" * len(header_str))

    def row(event, elapsed_val, pct, laps, driver="", crew=""):
        clock = format_clock(elapsed_val)
        miles = int(round(laps * track_miles))
        pct_s = f"{pct:.0f}%"
        parts = [
            f"{event:>{col_w[0]}}",
            f"{clock:>{col_w[1]}}",
            f"{pct_s:>{col_w[2]}}",
            f"{laps:>{col_w[3]}}",
            f"{miles:>{col_w[4]}}",
            f"{driver:>{col_w[5]}}",
            f"{crew:>{col_w[6]}}",
        ]
        print("  ".join(parts))

    row("Race Start", 0, 96.3, 0)

    for s in stints:
        laps_before = s["total_laps"] - s["laps"]
        if s["charge_start_elapsed"] is not None:
            crew_str = " + ".join(s["charge_crew"]) if s["charge_crew"] else ""
            row("Start Charge", s["charge_start_elapsed"], s["charge_start_pct"],
                laps_before, "-", crew_str)
            row("End Charge", s["charge_end_elapsed"], s["charge_target_pct"],
                laps_before, "-", crew_str)
            row("Buffer", s["buffer_end_elapsed"], s["charge_target_pct"],
                laps_before, "-")

        row("Start Stint", s["drive_start"], s["start_pct"], laps_before, s["driver"])
        row("End Stint", s["drive_end"], s["end_pct"], s["total_laps"], s["driver"])

    race_end = min(stints[-1]["drive_end"], race_minutes) if stints else 0
    row("Race End", race_end, stints[-1]["end_pct"] if stints else 96.3,
        stints[-1]["total_laps"] if stints else 0)

    # --- Driver summary ---
    print(f"\n{'='*60}")
    print("  DRIVER SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Driver':<10} {'Mode':<6} {'Stints':>6} {'Laps':>6} {'Drive Time':>11} {'Miles':>6}")
    print(f"  {'-'*50}")

    printed = set()
    for name in drivers:
        if name in printed:
            continue
        printed.add(name)
        ds = [s for s in stints if s["driver"] == name]
        total_laps_d = sum(s["laps"] for s in ds)
        total_min = sum(s["drive_end"] - s["drive_start"] for s in ds)
        h = int(total_min // 60)
        m = int(total_min % 60)
        miles = int(round(total_laps_d * track_miles))
        mode = drivers[name]["battery_mode"]
        print(f"  {name:<10} {mode:<6} {len(ds):>6} {total_laps_d:>6} {h:>3}h {m:02d}m       {miles:>6}")

    grand_laps = stints[-1]["total_laps"] if stints else 0
    grand_miles = int(round(grand_laps * track_miles))

    num_charges = sum(1 for s in stints if s["charge_start_elapsed"] is not None)
    total_charge_min = sum(
        s["charge_min"] + hookup_time
        for s in stints if s["charge_start_elapsed"] is not None
    )
    total_buffer_min = num_charges * charge_delay_time
    total_drive_min = sum(s["drive_end"] - s["drive_start"] for s in stints)

    print(f"\n  Total: {grand_laps} laps, {grand_miles} miles")
    print(f"  Drive time: {int(total_drive_min//60)}h {int(total_drive_min%60):02d}m")
    print(f"  Charge time: {int(total_charge_min//60)}h {int(total_charge_min%60):02d}m ({num_charges} charges)")
    print(f"  Buffer time: {int(total_buffer_min//60)}h {int(total_buffer_min%60):02d}m ({charge_delay_time:.0f}min x {num_charges})")
    print(f"{'='*60}\n")

    # --- Per-person plans (drivers + crew) ---
    all_people = list(drivers.keys()) + sorted(set(block_crew.values()))

    for name in all_people:
        is_driver = name in drivers

        # Stints this person drives
        drive_stints = [s for s in stints if s["driver"] == name] if is_driver else []
        # Charges this person supervises
        charge_stints = [s for s in stints if s["charge_crew"] and name in s["charge_crew"]]

        if not drive_stints and not charge_stints:
            continue

        # Merge into a timeline sorted by time
        events = []
        for s in drive_stints:
            events.append(("drive", s["drive_start"], s))
        for s in charge_stints:
            events.append(("charge", s["charge_start_elapsed"] - hookup_time, s))
        events.sort(key=lambda e: e[1])

        print(f"{'='*60}")
        if is_driver:
            d = drivers[name]
            mm = d["lap_time"] // 60
            ss = d["lap_time"] % 60
            print(f"  {name.upper()}'S PLAN  |  {d['battery_mode']} battery  |  {mm}:{ss:02d} laps  |  {d['pct_per_lap']}%/lap")
        else:
            print(f"  {name.upper()}'S PLAN  |  crew")
        print(f"{'='*60}")

        task_num = 0
        for event_type, _, s in events:
            task_num += 1
            print()
            if event_type == "charge":
                crew_str = " + ".join(s["charge_crew"])
                print(f"  Task {task_num}: Charge (with {crew_str})")
                print(f"    {format_clock(s['charge_start_elapsed'] - hookup_time):>10}  Connect for charging")
                print(f"    {format_clock(s['charge_start_elapsed']):>10}  Charging {s['charge_start_pct']:.0f}% → {s['charge_target_pct']:.0f}% ({s['charge_min']:.0f} min)")
                print(f"    {format_clock(s['buffer_end_elapsed']):>10}  Buffer done")
            else:
                print(f"  Task {task_num}: Drive")
                print(f"    {format_clock(s['drive_start']):>10}  Drive  ({s['start_pct']:.0f}% → {s['end_pct']:.0f}%)")
                drive_min = s["drive_end"] - s["drive_start"]
                h = int(drive_min // 60)
                m = int(drive_min % 60)
                print(f"    {format_clock(s['drive_end']):>10}  Done   ({s['laps']} laps, {int(round(s['laps'] * track_miles))} mi, {h}h {m:02d}m)")

        if is_driver:
            total_laps_d = sum(s["laps"] for s in drive_stints)
            total_min = sum(s["drive_end"] - s["drive_start"] for s in drive_stints)
            h = int(total_min // 60)
            m = int(total_min % 60)
            print(f"\n  Drive total: {len(drive_stints)} stints, {total_laps_d} laps, {int(round(total_laps_d * track_miles))} mi, {h}h {m:02d}m")
        print(f"  Charge duties: {len(charge_stints)}")
        print()


if __name__ == "__main__":
    optimal_pct = find_optimal_charge_level()
    print(f"Optimal full-battery charge target: {optimal_pct}%")
    stints = build_schedule(optimal_pct)
    print_schedule(stints, optimal_pct)
