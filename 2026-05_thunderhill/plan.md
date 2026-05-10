# Thunderhill 25hr Race Plan Generator

## Race format
- **25 hours straight**: Sat 11am → Sun 12pm, no breaks
- **Track**: Thunderhill 3-mile layout
- **Car**: Chevy Bolt EV, 62 kWh usable pack
- **Min battery**: 10% (was 20% at Sonoma)
- **Start battery**: 96.3%

## Driver blocks

| Block | Window | Hours | Drivers |
|-------|--------|-------|---------|
| 1 | Sat 11am–3pm | 4h | Alexey, Yezhi, Roman |
| 2 | Sat 3pm–Sun 3am | 12h | Forrest, Xiaoyu, Amethyst |
| 3 | Sun 3am–12pm | 9h | Alexey, Yezhi, Roman |

## Driver preferences

| Driver | Lap time (s) | Battery mode |
|--------|-------------|--------------|
| Alexey | 150 | Full |
| Yezhi | 160 | Full |
| Roman | 170 | Full |
| Forrest | 160 | Half |
| Xiaoyu | 170 | Half |
| Amethyst | 160 | Full |

- **Full battery**: charge up to optimal level, drive down to 10%
- **Half battery**: charge to ~50%, drive down to 10%

## Battery consumption (`lap_data`)

Derived from 2025 Thunderhill race data (204 laps, 5 charge sessions). Fitted `pct_per_lap = f(speed)` against actual stint lengths.

| Lap time | Min:Sec | mph | %/lap | Laps for 80% | Stint time |
|----------|---------|-----|-------|--------------|------------|
| 150s | 2:30 | 72.0 | 3.4% | 24 | 59 min |
| 160s | 2:40 | 67.5 | 2.9% | 28 | 74 min |
| 170s | 2:50 | 63.5 | 2.5% | 32 | 91 min |
| 180s | 3:00 | 60.0 | 2.2% | 36 | 109 min |
| 190s | 3:10 | 56.8 | 1.9% | 42 | 133 min |
| 200s | 3:20 | 54.0 | 1.7% | 47 | 157 min |
| 210s | 3:30 | 51.4 | 1.5% | 53 | 187 min |

## Charge model (`charge_data`)

Same Bolt charger curve as Sonoma, shifted to start at 10% (subtract 5.3 min):

```
[10, 0.0],  [15, 2.7],  [20, 5.3],  [25, 8.0],  [30, 10.7],
[35, 13.3], [40, 16.0], [45, 18.7], [50, 21.3], [55, 24.0],
[60, 26.7], [65, 29.3], [70, 31.9], [75, 35.7], [80, 39.4],
[85, 43.2], [90, 46.9], [92, 48.2], [93, 49.4], [94, 50.3],
[94.4, 51.5]
```

## Timing constants
- **Hookup time**: 5 min (plug in charger)
- **Buffer after charge**: 15 min (slow laps, traffic, race stoppages)

## How the simulator works

1. **Define each driver**: name, lap_time, pct_per_lap, battery_mode (full/half)
2. **For each block**, rotate through that block's drivers in order
3. **Each driver's stint**:
   - Full battery driver: drive from current charge level down to 10%
   - Half battery driver: drive from ~50% down to 10%
4. **Between stints**: charge to what the *next* driver needs
   - Next driver wants full → charge to optimal level (maximize total laps)
   - Next driver wants half → charge to ~50%
5. **Final stint of the race**: drain to 5% instead of 10%
6. **Charge overhead per stop**: 5 min hookup + charge time + 15 min buffer

## What to optimize

For full-battery drivers, try multiple charge target levels from the charge_data table and pick the one that maximizes total laps across the entire race.

## Output

- Event log with: clock time, event type, battery %, cumulative laps, miles, **driver name**
- Per-driver summary: total laps, total driving time, total miles
- Overall: total laps, total miles, time on track vs charging

## File
`2026-05_thunderhill/may_2026_thunderhill_25hr.py`

Run with: `/Users/fni/miniconda3/envs/feb2026/bin/python 2026-05_thunderhill/may_2026_thunderhill_25hr.py`
