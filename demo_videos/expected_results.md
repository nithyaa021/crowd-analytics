# Expected results on the demo clips

Measured with the real pipeline: `Detector` (YOLOv8 nano + ByteTrack), `conf=0.35`, every 2nd frame, frames resized to 640 px wide.

| Clip | Scenario | Source | Length | Max people | Median people | Fits role | Expected alert |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `normal.mp4` | normal | `36304379.mp4` | 24.4s | 4 | 2 | yes | None - stays under capacity |
| `mid.mp4` | mid | `14393753.mp4` | 31.1s | 12 | 5 | yes | Maybe - a low-capacity zone can fill up |
| `crowded.mp4` | crowded | `18516076.mp4` | 45.0s | 15 | 8 | yes | Yes - zone goes over capacity |

## How to read the table

- **Max people** is the busiest single frame; it decides the role. Expected: normal <= 6, mid 7-14, crowded >= 12.
- **Median people** is the typical frame; it shows how often the scene is busy, not just whether it spikes once.
- A clip that does not fit is reported, never renamed silently. Replace the raw file or agree a new role name.

## Clip details

### normal.mp4

- Source file: `demo_videos/raw/36304379.mp4`
- Used stretch: 0.0s to 24.4s (24.4s, cut-free)
- Written resolution: 1280x720 (downscaled from the original, still 720p or better)
- First/last preview difference: 18.8 (warning above 35)

### mid.mp4

- Source file: `demo_videos/raw/14393753.mp4`
- Used stretch: 0.0s to 31.1s (31.1s, cut-free)
- Written resolution: 1280x720 (downscaled from the original, still 720p or better)
- First/last preview difference: 35.4 (warning above 35)

### crowded.mp4

- Source file: `demo_videos/raw/18516076.mp4`
- Used stretch: 0.0s to 45.0s (45.0s, cut-free)
- Written resolution: 1280x720 (downscaled from the original, still 720p or better)
- First/last preview difference: 14.5 (warning above 35)

## Camera stability

Each clip is written from a single stretch between detected cuts, so there is no scene
change inside a clip. The preview number is a raw pixel-change score, which moving
people raise even when the camera is still; the script warns when it crosses 35, and the preview images were then checked by eye.
