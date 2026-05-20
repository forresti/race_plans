# Thunderhill 25hr Race Plan Generator

## Race format
- **25 hours straight**: Sat 11am → Sun 12pm, no breaks
- **Track**: Thunderhill 3-mile layout (2.866 mi)
- **Car**: Chevy Bolt EV, 62 kWh usable pack
- **Min battery**: 10% (5% for final stint)
- **Start battery**: 96.3%
- **Charge target**: 94%

## Daylight (Willows, CA, May 23)
- Sunset ~7:20 PM, sunrise ~4:56 AM
- Night (headlights needed): ~8 PM – 5:30 AM

## Driver info

| Driver | Lap time (s) | %/lap | Source |
|--------|-------------|-------|--------|
| Alexey | 160 (2:40) | 2.8 | Actual data from 2025 race, P30 at 160s |
| Yezhi | 160 (2:40) | 2.8 | Mimics Alexey |
| Roman | 170 (2:50) | 2.2 | Mimics Xiaoyu |
| Forrest | 160 (2:40) | 2.2 | Actual data (was hypermiling in 2025, adjusted) |
| Xiaoyu | 170 (2:50) | 2.2 | Actual data from 2025 race, P30 at 170s |
| Amethyst | 160 (2:40) | 2.1 | Actual data from 2025 race, P30 at 160s |

Battery %/lap derived from "Driver graphs - all" tab of `2025-05_thunderhill_25hr.xlsx`, using P30 (30th percentile, lower is better) per driver at their target lap time (±5s window).

Amethyst is slightly more efficient than Forrest at any pace due to skill.

## Sleep schedule constraints
- **Done by 3 AM**: Forrest, Amethyst
- **Start at 3 AM**: Alexey, Yezhi, Roman
- **No overlap** between the two groups

## Driver-specific constraints
- **Xiaoyu**: No night driving. Done by 8 PM, back at 9 AM. Half stints only.
- **Alexey**: Prefers full stints. Starts the race (fast laps on cold car).
- **Amethyst**: Prefers full stints.
- **Yezhi, Roman, Forrest**: Flexible on stint size.

## Crew members
- **Luns**: Crew for blocks with Alexey (morning + early morning shifts)
- **Jen**: Crew for blocks with Forrest/Xiaoyu/Amethyst (afternoon + night shifts)
- 2 people must supervise every charge session
- Neither the previous driver nor the next driver can be on charge crew
- Crew member is always one of the two; the other is a non-driving teammate
- Charge duties are balanced across drivers using a greedy algorithm with future-opportunity tiebreaking

## Stint sequence

The race is driven as a fixed sequence of stints, not rotating blocks. "Shared battery" means two drivers split one charge: first driver goes 94→52%, swap (5 min), second driver goes 52→10%.

### Morning (Sat ~11am–3pm): Alexey, Yezhi, Roman
1. Alexey full (burns starting 96.3%)
2. Charge → Yezhi half + Roman half (shared)

### Afternoon (Sat ~3pm–8pm): Xiaoyu, Forrest, Amethyst
3. Charge → Xiaoyu half + Forrest half (shared). Xiaoyu must finish by 8 PM.
4. Charge → Amethyst full

### Night (Sat ~9pm–3am): Forrest, Amethyst
5. Charge → Forrest full
6. Charge → Amethyst (truncated at 3 AM deadline)

### Early morning (Sun ~3am–9am): Yezhi, Alexey, Roman
7. Yezhi drives remaining battery from Amethyst's truncated stint (no charge)
8. Charge → Alexey full
9. Charge → Roman full

### Late morning (Sun ~10am–12pm): Xiaoyu, Yezhi
10. Charge → Xiaoyu half + Yezhi half (shared). Xiaoyu back at 9 AM.

## Charge model

Same Bolt charger curve as Sonoma, shifted to start at 10% (subtract 5.3 min):

```
[10, 0.0],  [15, 2.7],  [20, 5.3],  [25, 8.0],  [30, 10.7],
[35, 13.3], [40, 16.0], [45, 18.7], [50, 21.3], [55, 24.0],
[60, 26.7], [65, 29.3], [70, 31.9], [75, 35.7], [80, 39.4],
[85, 43.2], [90, 46.9], [92, 48.2], [93, 49.4], [94, 50.3],
[94.4, 51.5]
```

## Timing constants
- **Hookup time**: 5 min (connect for charging)
- **Buffer after charge**: 20 min (slow laps, traffic, race stoppages)
- **Driver swap time**: 5 min (mid-battery driver change)
- **Charge cycle total**: ~75 min (5 hookup + 50 charge + 20 buffer)

## Why 94% charge target?
- 80% maximizes laps (312 vs 307 at 90%) because 70→90% charges at slower 50kW rate
- But 94% gives 8 charges instead of 10, and the race ends cleanly without a wasted final charge cycle
- Less thrash for the team is worth the small lap count tradeoff

## Stint durations at 94%
| Driver | Full stint | Half stint |
|--------|-----------|------------|
| Alexey/Yezhi (2.8%/lap, 160s) | 30 laps, 80 min | 15 laps, 40 min |
| Roman/Xiaoyu (2.2%/lap, 170s) | 38 laps, 108 min | 19 laps, 54 min |
| Forrest (2.2%/lap, 160s) | 38 laps, 101 min | 19 laps, 51 min |
| Amethyst (2.1%/lap, 160s) | 40 laps, 107 min | 20 laps, 53 min |

## Output
- Main schedule: event log with clock time, battery %, laps, miles, driver, charge crew
- Driver summary: stints, laps, drive time, miles
- Per-person plans (drivers + crew): timeline of drive and charge tasks
- Race totals: laps, miles, drive time, charge time, buffer time

## Current results (as of latest run)
- **318 laps, 911 miles**
- **8 charges**
- Drive time: 14h 23m
- All drivers except Xiaoyu at 2hr+
- Xiaoyu at 1h 47m (needs one more half stint to hit 2hr target)

## File
`2026-05_thunderhill/may_2026_thunderhill_25hr.py`

Run with: `/Users/fni/miniconda3/envs/feb2026/bin/python 2026-05_thunderhill/may_2026_thunderhill_25hr.py`
