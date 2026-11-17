"""Render a side-by-side video of a judged recorded pair (TASK_DIR/bro, TASK_DIR/bu), with real-time timers.

Needs Pillow, so it runs in the browser-use environment (PYTHONPATH=.):

    .venv-browser-use/bin/python -m bro.bench.compare.render out/EWV-001-Allrecipes out/EWV-001-Allrecipes.mp4 \
        --model-label "Qwen3.6-35B-A3B 2-bit, local"
"""

import argparse
import bisect
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

from .models import RecordedRun, ScreencastIndex

WIDTH, BODY, TOP, BOTTOM, FPS = 960, 720, 84, 70, 10
FONT = "/System/Library/Fonts/Helvetica.ttc"
NAMES = {"bro": "Bro fast loop", "bu": "browser-use 1.0.3"}


def load_side(side_dir: Path) -> Tuple[ScreencastIndex, RecordedRun]:
    index = ScreencastIndex(**json.loads((side_dir / "frames" / "index.json").read_text()))
    return index, RecordedRun(**json.loads((side_dir / "result.json").read_text()))


def frame_at(index: ScreencastIndex, frames_dir: Path, t: float) -> Path:
    times = [f[0] for f in index.frames]
    i = max(bisect.bisect_right(times, t) - 1, 0)
    return frames_dir / index.frames[i][1]


def render(task_dir: Path, out: Path, model_label: str) -> None:
    task_text = (task_dir / "task.txt").read_text().strip()
    sides = [(name, *load_side(task_dir / name)) for name in ("bro", "bu")]
    total = max(run.elapsed_s for _, _, run in sides) + 2.5
    label_font, timer_font, task_font = ImageFont.truetype(FONT, 26), ImageFont.truetype(FONT, 24), ImageFont.truetype(FONT, 18)
    tmp = Path(tempfile.mkdtemp())
    cache: Dict[Path, Image.Image] = {}
    for k in range(int(total * FPS)):
        t = k / FPS
        canvas = Image.new("RGB", (2 * WIDTH, TOP + BODY + BOTTOM), (17, 17, 17))
        draw = ImageDraw.Draw(canvas)
        for i, (name, index, run) in enumerate(sides):
            x0, shown = i * WIDTH, min(t, run.elapsed_s)
            if index.frames:
                path = frame_at(index, task_dir / name / "frames", shown)
                if path not in cache:
                    image = Image.open(path).convert("RGB")
                    image.thumbnail((WIDTH, BODY))
                    cache = {path: image}
                image = cache[path]
                canvas.paste(image, (x0 + (WIDTH - image.width) // 2, TOP + (BODY - image.height) // 2))
            draw.text((x0 + 20, 12), f"{NAMES[name]}   {model_label}", font=label_font, fill="white")
            draw.text((x0 + 20, 48), f"{shown:5.1f} s", font=timer_font, fill=(255, 216, 77))
            if t >= run.elapsed_s:
                status = f"{'PASS' if run.success else 'FAIL'}   {run.steps} steps"
                colour = (94, 224, 138) if run.success else (255, 112, 112)
                draw.text((x0 + WIDTH - 20 - draw.textlength(status, font=timer_font), 48), status, font=timer_font, fill=colour)
        draw.line([(WIDTH, 0), (WIDTH, TOP + BODY)], fill=(60, 60, 60), width=2)
        lines: List[str] = [task_text[:170], task_text[170:340]]
        for row, line in enumerate(line for line in lines if line):
            draw.text((20, TOP + BODY + 12 + 26 * row), line, font=task_font, fill="white")
        canvas.save(tmp / f"{k:06d}.jpg", quality=85)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "%06d.jpg"),
                    "-r", "30", "-pix_fmt", "yuv420p", "-vcodec", "libx264", "-crf", "23", str(out)], check=True)
    shutil.rmtree(tmp)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("task_dir")
    parser.add_argument("out")
    parser.add_argument("--model-label", default="Qwen3.6-35B-A3B 2-bit, local")
    args = parser.parse_args()
    render(Path(args.task_dir), Path(args.out), args.model_label)
