# Expected results on the demo clips

These are the numbers the real pipeline produces, so you can check the app is behaving
correctly. Same settings for all three clips: YOLOv8 nano + ByteTrack, `conf=0.35`,
every 2nd frame analysed, frames resized to 640 px wide.

| Clip | Scenario | Length | Max people | Median people | Capacity set in `zones.json` | Expected alert |
| --- | --- | --- | --- | --- | --- | --- |
| `normal.mp4` | normal | 24.4 s | 4 | 2 | 4 | **None** — stays under capacity |
| `mid.mp4` | mid | 31.1 s | 12 | 5 | 5 | **None** — spikes are too short to sustain 3 s |
| `crowded.mp4` | crowded | 45.0 s | 15 | 8 | 4 | **Yes** — one alert at about 31.5 s |

## How to read the table

- **Max people** is the busiest single analysed frame across the whole clip.
- **Median people** is the typical frame, so it shows how often the scene is busy rather than
  whether it spiked once.
- **Capacity** is deliberately chosen per clip: `crowded.mp4` is meant to go over so there is an
  alert to demonstrate, and `normal.mp4` is meant to stay comfortably under so we can prove the
  app does not raise false alarms.

## The expected behaviour, in detail

### normal.mp4 — the false-positive check

Low density. The zone count hovers around 2 and peaks at 4, which equals capacity but never
exceeds it. `status_for` returns **NEAR** at 4/4 (80% or more of capacity), never **OVER**.

Result: **0 alerts** over a full loop. This is the test that proves an empty scene does not set
off the alarm.

### mid.mp4 — the near miss

Busier, median 5, with brief spikes above the capacity of 5. But every spike lasts less than
`ON_DELAY` (3 s), so `AlertDebouncer` never fires. That is the debouncer doing its job: a
momentary bump is noise, not a crowd.

Result: **0 alerts**.

### crowded.mp4 — the demonstration

Dense and sustained. The zone holds more than 4 people for well over 3 seconds, starting around
video time 28.5 s.

Result: **1 alert**, fired at about **31.5 s**, with a peak of **8 / 4**. Because
`OFF_DELAY` is 5 s and the crowd never fully disperses before the clip ends, the alert stays open
until the clip stops and is then closed by `_close_alerts`.

Evidence photo: `evidence/alert_1.jpg` — the frame that caused it, with boxes, foot points, the
zone polygon and an `ALERT 1  31.5s` stamp drawn in.

## Why the clips never cut mid-scene

Each clip is a single continuous stretch, so there is no scene change inside a clip. That keeps
the zone polygons valid for the whole video — a camera cut would move the floor under the
polygon and every count would be wrong.

## What to do if your numbers differ slightly

The detector is not bit-for-bit deterministic across machines, and a slower CPU changes how many
frames finish before the clip ends. Small differences are normal. What must hold:

1. `normal.mp4` and `mid.mp4` produce **no** alerts.
2. `crowded.mp4` produces **at least one** alert, with a peak above 4.
3. The headcount chart in the dashboard visibly rises during `crowded.mp4` and stays flat during
   `normal.mp4`.

If `crowded.mp4` never alerts, the likely cause is a CPU slow enough that the 3-second sustained
run is not reached; lower `ON_DELAY` in `app/config.py` and note the change.
