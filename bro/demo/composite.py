"""Composite the demo video: your screen recording + Bro's invisible browser (picture-in-picture, bottom right) + a live
panel drawn from the logged timeline (top right). Needs the `demo` extra (Pillow) and ffmpeg.

    uv run python -m bro.demo.composite demo-runs/take-1 ~/Desktop/"Screen Recording 2026-11-18 at 19.03.12.mov" demo.mp4

The recording's start time comes from --start HH:MM:SS, else from the macOS file name, else from its creation_time tag.
--speed N plays everything N times faster and labels the panel with the factor.
"""

import argparse
import bisect
import datetime as dt
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

from bro.bench.compare.models import ScreencastIndex

from .models import Timeline

FONT = "/System/Library/Fonts/Helvetica.ttc"
PANEL_W, PANEL_H, PANEL_FPS = 560, 470, 4
GREEN, RED, YELLOW, GREY = (94, 224, 138), (255, 112, 112), (255, 216, 77), (150, 150, 150)


def recording_start(path: Path, start_hms: str) -> float:
    day = dt.date.today()
    # macOS names recordings "Screen Recording 2026-11-18 at 19.30.11.mov" or, with a 12-hour clock, "... at 7.30.11 PM.mov"
    match = re.search(r"(\d{4}-\d{2}-\d{2}) at (\d{1,2})\.(\d{2})\.(\d{2})\s*([AP]M)?", path.name)
    if match:
        day = dt.date.fromisoformat(match.group(1))
    if start_hms:
        h, m, s = map(int, start_hms.split(":"))
        return dt.datetime.combine(day, dt.time(h, m, s)).timestamp()
    if match:
        hour = int(match.group(2)) % 12 + (12 if match.group(5) == "PM" else 0) if match.group(5) else int(match.group(2))
        return dt.datetime.combine(day, dt.time(hour, int(match.group(3)), int(match.group(4)))).timestamp()
    tag = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=creation_time", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    return dt.datetime.fromisoformat(tag.replace("Z", "+00:00")).timestamp()


def browser_video(run: Path, tmp: Path) -> Path:
    """Bro's screencast frames as a real-time video, 640 px wide."""
    index = ScreencastIndex(**json.loads((run / "frames" / "index.json").read_text()))
    frames = index.frames
    lines: List[str] = []
    for i, (t, name) in enumerate(frames):
        nxt = frames[i + 1][0] if i + 1 < len(frames) else index.end
        lines += [f"file '{run / 'frames' / name}'", f"duration {max(nxt - t, 0.001):.3f}"]
    lines.append(f"file '{run / 'frames' / frames[-1][1]}'")
    (tmp / "concat.txt").write_text("\n".join(lines))
    out = tmp / "browser.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "concat.txt"),
                    # a black frame so the picture-in-picture stays visible over white pages
                    "-vf", f"tpad=start_duration={frames[0][0]:.3f}:start_mode=clone,scale=640:-2,fps=15,pad=iw+8:ih+8:4:4:black",
                    "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


def task_line(label: str, start: float, end: float, answer: bool, t: float) -> Tuple[Tuple[int, int, int], str]:
    if 0 < end <= t:
        return (GREEN, f"{label}  {end - start:.0f} s") if answer else (RED, f"{label}  no answer")
    if start <= t:
        return YELLOW, f"{label}  {t - start:.0f} s"
    return GREY, label


def panel_video(timeline: Timeline, speed: float, tmp: Path) -> Path:
    """The live panel as a transparent video: timer, tasks done, memory, focus count and the task checklist."""
    big, mid, small = ImageFont.truetype(FONT, 30), ImageFont.truetype(FONT, 20), ImageFont.truetype(FONT, 17)
    tasks, samples = timeline.tasks, timeline.samples
    total = (timeline.end or tasks[-1].end) + 3
    times = [s.t for s in samples]
    frames_dir = tmp / "panel"
    frames_dir.mkdir()
    for k in range(int(total * PANEL_FPS)):
        t = k / PANEL_FPS
        image = Image.new("RGBA", (PANEL_W, PANEL_H), (15, 15, 15, 225))
        draw = ImageDraw.Draw(image)
        free = samples[max(bisect.bisect_right(times, t) - 1, 0)].free_pct if samples else 0
        stolen = sum(1 for s in samples if s.t <= t and s.agent_front)
        finished = sum(1 for x in tasks if 0 < x.end <= t)
        draw.text((18, 12), "Bro, working in the background", font=mid, fill="white")
        draw.text((18, 42), f"{int(t // 60)}:{int(t % 60):02d}", font=big, fill=YELLOW)
        if speed != 1:
            draw.text((PANEL_W - 70, 48), f"{speed:g}x", font=mid, fill=GREY)
        draw.text((130, 50), f"{finished}/{len(tasks)} tasks done", font=mid, fill="white")
        draw.text((18, 86), "local model, capped at 12 GB", font=small, fill="white")
        draw.text((18, 108), f"free system memory {free}%", font=small, fill="white")
        draw.text((300, 86), "focus taken by Bro:", font=small, fill="white")
        draw.text((300, 106), f"{stolen} times", font=mid, fill=GREEN if stolen == 0 else RED)
        y = 142
        for x in tasks:
            colour, text = task_line(x.label, x.start, x.end, bool(x.answer), t)
            draw.ellipse((20, y + 7, 32, y + 19), fill=colour)
            draw.text((44, y + 2), text, font=small, fill="white" if x.start <= t else GREY)
            y += 31
        image.save(frames_dir / f"{k:06d}.png")
    out = tmp / "panel.mov"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(PANEL_FPS), "-i", str(frames_dir / "%06d.png"),
                    "-c:v", "qtrle", "-pix_fmt", "argb", str(out)], check=True)
    return out


def composite(run: Path, recording: Path, out: Path, speed: float, start_hms: str, tight: bool) -> float:
    timeline = Timeline(**json.loads((run / "timeline.json").read_text()))
    offset = max(timeline.start_epoch - recording_start(recording, start_hms), 0)
    tmp = Path(tempfile.mkdtemp())
    browser, panel = browser_video(run, tmp), panel_video(timeline, speed, tmp)
    trim = ""
    if tight:  # from 3 s before Bro starts to 3 s after its last task, in output time
        first = max(offset - 3, 0) / speed
        last = (offset + (timeline.end or timeline.tasks[-1].end) + 3) / speed
        trim = f",trim=start={first:.3f}:end={last:.3f},setpts=PTS-STARTPTS"
    graph = (f"[0:v]scale=1920:-2,setpts=PTS/{speed}[base];"
             f"[1:v]setpts=(PTS+{offset:.3f}/TB)/{speed}[pip];"
             f"[2:v]setpts=(PTS+{offset:.3f}/TB)/{speed}[pan];"
             "[base][pip]overlay=W-w-24:H-h-24:eof_action=pass[v1];"
             f"[v1][pan]overlay=W-w-24:24:eof_action=repeat{trim},format=yuv420p[v]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(recording), "-i", str(browser), "-i", str(panel),
                    "-filter_complex", graph, "-map", "[v]", "-an", "-r", "30", "-c:v", "libx264", "-crf", "22", str(out)], check=True)
    shutil.rmtree(tmp)
    return offset


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    parser.add_argument("recording")
    parser.add_argument("out")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--start", default="", help="recording start time HH:MM:SS if the file name has none")
    parser.add_argument("--tight", action="store_true", help="keep only 3 s before Bro starts to 3 s after it finishes")
    args = parser.parse_args()
    offset = composite(Path(args.run).resolve(), Path(args.recording).expanduser().resolve(), Path(args.out).expanduser(),
                       args.speed, args.start, args.tight)
    print(f"wrote {args.out} (Bro started {offset:.1f} s into the recording)")
