from math import floor

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

hookup_time = 5  # minutes to hook up to the charger
charge_delay_time = 20  # minutes buffer after charging
driver_swap_time = 5  # minutes for mid-battery driver change
track_miles = 2.866

# --- Driver definitions ---

drivers = {
    "Alexey": {"lap_time": 160, "pct_per_lap": 2.8},
    "Yezhi": {"lap_time": 160, "pct_per_lap": 2.8},
    "Roman": {"lap_time": 170, "pct_per_lap": 2.2},
    "Forrest": {"lap_time": 160, "pct_per_lap": 2.2},
    "Xiaoyu": {"lap_time": 170, "pct_per_lap": 2.2},
    "Amethyst": {"lap_time": 160, "pct_per_lap": 2.1},
}

race_start_hour = 11
race_minutes = 25 * 60

# Crew members: 2 people must supervise charging.
# Neither can be the driver before or after the charge.
# Blocks with Alexey get Luns, others get Jen.
# Crew schedule:
#   Sergey: Sat 11am-3pm, Sun 7am-noon
#   Luns:   Sat 3pm - Sun 3am
#   No crew: Sun 3am-7am (only drivers available to charge)
#
# Blocks define which drivers + crew are available at each time.
# Used for charge crew assignment (find 2 people to supervise charging).
blocks = [
    (0, 4, ["Yezhi", "Roman", "Xiaoyu"]),          # Sat 11am-3pm
    (4, 16, ["Forrest", "Xiaoyu", "Amethyst"]),     # Sat 3pm-3am
    (16, 20, ["Alexey", "Yezhi", "Roman"]),         # Sun 3am-7am (no crew)
    (20, 25, ["Yezhi", "Roman", "Xiaoyu"]),         # Sun 7am-noon
]

block_crew: dict[int, str | None] = {
    0: "Sergey",
    1: "Luns",
    2: None,       # no crew available 3am-7am
    3: "Sergey",
}


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
            bi2 = get_block_for_time(s2["charge_start_elapsed"])
            _, _, bd2 = blocks[bi2]
            crew2 = block_crew[bi2]
            if person in bd2 or person == crew2:
                count += 1
    return count


def assign_charge_crews(stints: list[dict]) -> None:
    """Assign charge crews to all stints, balancing duties across people."""
    charge_counts: dict[str, int] = {}
    for s in stints:
        if s["charge_start_elapsed"] is None:
            continue

        idx = stints.index(s)
        prev_driver = stints[idx - 1]["driver"] if idx > 0 else None
        next_driver = s["driver"]

        bi = get_block_for_time(s["charge_start_elapsed"])
        _, _, block_drivers = blocks[bi]
        crew = block_crew[bi]

        excluded = {next_driver}
        if prev_driver:
            excluded.add(prev_driver)
        available_drivers = [p for p in block_drivers if p not in excluded]

        # Pick the available driver with fewest charge duties so far.
        # Break ties by fewest future opportunities (prefer harder-to-schedule people).
        if available_drivers:
            available_drivers.sort(key=lambda p: (
                charge_counts.get(p, 0),
                future_opportunities(p, stints, idx),
            ))
            picked = available_drivers[0]
        else:
            picked = crew if crew else next_driver

        if crew:
            s["charge_crew"] = [picked, crew]
        else:
            # No crew available — need 2 drivers
            remaining = [p for p in available_drivers if p != picked]
            if remaining:
                remaining.sort(key=lambda p: charge_counts.get(p, 0))
                s["charge_crew"] = [picked, remaining[0]]
                charge_counts[remaining[0]] = charge_counts.get(remaining[0], 0) + 1
            else:
                s["charge_crew"] = [picked]
        charge_counts[picked] = charge_counts.get(picked, 0) + 1
        if crew:
            charge_counts[crew] = charge_counts.get(crew, 0) + 1

# --- Stint sequence ---
# (driver, charge_mode, deadline_minutes_from_start)
# charge_mode: "full" = charge to CHARGE_TARGET, None = drive on current battery
# deadline: latest time this stint can end
#
# Crew:
#   Sergey: Sat 11am-3pm, Sun 7am-noon
#   Luns: Sat 3pm - Sun 3am
#   No crew: Sun 3am-7am
#
# Constraints:
#   Xiaoyu: no night driving. Done by 8pm, back at 9am. Half stints.
#   Forrest, Amethyst: done by 3am
#   Alexey: both stints back-to-back at night (3am-7am, no crew window)
#   Everyone: target 2hr+ track time
#
# Sunset ~7:20pm, sunrise ~5am. Night = ~8pm-5:30am.

stint_sequence = [
    # Morning (Sat 11am-~3pm, crew: Sergey)
    ("Yezhi", None, 25 * 60),        # burns starting 96.3%
    ("Xiaoyu", "full", 9 * 60),      # charge, Xiaoyu half. Must end by 8pm
    ("Roman", None, 25 * 60),        # Roman half (shared)
    # Afternoon (Sat ~3pm-8pm, crew: Luns)
    ("Xiaoyu", "full", 9 * 60),      # charge, Xiaoyu half. Must end by 8pm
    ("Forrest", None, 25 * 60),      # Forrest half (shared)
    ("Amethyst", "full", 25 * 60),   # charge, Amethyst full
    # Night (Sat ~9pm-3am, crew: Luns)
    ("Forrest", "full", 16 * 60),    # charge, Forrest full. Must end by 3am
    ("Amethyst", "full", 16 * 60),   # charge, Amethyst (truncated at 3am)
    # Deep night (Sun 3am-7am, no crew): Alexey back-to-back
    ("Yezhi", None, 25 * 60),        # drives remaining battery from Amethyst
    ("Alexey", "full", 25 * 60),     # charge (Yezhi+Roman), Alexey full
    ("Alexey", "full", 25 * 60),     # charge (Yezhi+Roman), Alexey full
    # Sunday morning (Sun 7am-noon, crew: Sergey)
    ("Roman", "full", 25 * 60),      # charge, Roman full
    ("Xiaoyu", "full", 25 * 60),     # charge, Xiaoyu half
    ("Yezhi", None, 25 * 60),        # Yezhi drives remaining battery
]

CHARGE_TARGET = 94


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
        # But don't override shared battery splits — the next driver needs battery
        if not next_is_shared:
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
    print(f"  {'Driver':<10} {'Lap':>5} {'%/lap':>6} {'Stints':>6} {'Laps':>6} {'Drive Time':>11} {'Miles':>6}")
    print(f"  {'-'*55}")

    printed = set()
    for name in drivers:
        if name in printed:
            continue
        printed.add(name)
        d = drivers[name]
        lap_mm = d["lap_time"] // 60
        lap_ss = d["lap_time"] % 60
        ds = [s for s in stints if s["driver"] == name]
        total_laps_d = sum(s["laps"] for s in ds)
        total_min = sum(s["drive_end"] - s["drive_start"] for s in ds)
        h = int(total_min // 60)
        m = int(total_min % 60)
        miles = int(round(total_laps_d * track_miles))
        print(f"  {name:<10} {lap_mm}:{lap_ss:02d} {d['pct_per_lap']:>5.1f}% {len(ds):>6} {total_laps_d:>6} {h:>3}h {m:02d}m       {miles:>6}")

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
    all_people = list(drivers.keys()) + sorted(c for c in set(block_crew.values()) if c)

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
            print(f"  {name.upper()}'S PLAN  |  {mm}:{ss:02d} laps  |  {d['pct_per_lap']}%/lap")
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
    stints = build_schedule(CHARGE_TARGET)
    print_schedule(stints, CHARGE_TARGET)
