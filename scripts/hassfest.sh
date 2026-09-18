#!/usr/bin/env bash
# Docker may run outside the self-hosted runner container. Copy files instead of
# bind-mounting a runner-only path that the Docker daemon cannot see.
set -euo pipefail
hassfest_container=$(docker create ghcr.io/home-assistant/hassfest)
trap 'docker rm -f "$hassfest_container" >/dev/null' EXIT
docker cp custom_components "$hassfest_container:/github/workspace/custom_components"
docker start --attach "$hassfest_container"
test "$(docker inspect --format '{{.State.ExitCode}}' "$hassfest_container")" = 0
