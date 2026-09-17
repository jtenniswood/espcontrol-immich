#!/usr/bin/with-contenv bashio
set -euo pipefail

mkdir -p /data
export IMMICH_FRAMES_CONFIG=/data/config.json
python -m immich_frames

