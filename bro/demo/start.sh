#!/bin/zsh
# 'Works while you work' demo.
#   1. Start a screen recording (Cmd+Shift+5, "Record Entire Screen").
#   2. Run bro/demo/start.sh from anywhere, then go back to what you were doing.
#   3. Stop the recording after the "All 10 tasks done" notification and run the composite command printed at the end.
# Needs: `uv sync --extra demo`, the splash CLI, ffmpeg.
set -e
ROOT=${0:A:h:h:h}
cd $ROOT
OUT=$ROOT/demo-runs/take-$(date +%Y%m%d-%H%M%S)
mkdir -p $ROOT/demo-runs
export BRO_LOCAL_BASE_URL=${BRO_LOCAL_BASE_URL:-http://127.0.0.1:8001/v1}
if ! curl -s -o /dev/null -m 2 $BRO_LOCAL_BASE_URL/models; then
  echo "loading the local model (about 20 s)..."
  splash serve --model unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q2_K_XL --max-memory 12G --idle-release off \
    --served-model-name mlx-community/Qwen3.6-35B-A3B-4bit --announce-served-name --port 8001 --no-webui \
    > $ROOT/demo-runs/splash.log 2>&1 &
  until curl -s -o /dev/null -m 2 $BRO_LOCAL_BASE_URL/models; do sleep 2; done
fi
echo "model ready; Bro starts in 5 s. Go do your homework."
sleep 5
uv run --quiet python -m bro.demo.run bro/demo/tasks.json $OUT 2>&1 | grep -v "LiteLLM" | grep -v "^20..-..-.. "
echo
echo "Run saved to $OUT"
echo "Stop your recording, then:"
echo "  cd $ROOT && uv run python -m bro.demo.composite $OUT ~/Desktop/'Screen Recording <date> at <time>.mov' ~/Desktop/bro-demo.mp4"
echo "To unload the model afterwards: pkill -f 'splash serve'"
