#!/usr/bin/env bash
# Publish a committed snapshot to production (https://h21.ariel.tools).
#
#   deploy/deploy.sh            deploy the tip of master
#   deploy/deploy.sh <commit>   deploy a specific commit, e.g. to roll back
#
# Each commit becomes its own release directory with its own virtualenv, built from
# `git archive` so only committed files go live. `current` points at the live release,
# and the three newest releases are kept for rollback. Runs as a user service, so no
# step here needs sudo. The OpenAI key comes from ~/.local/share/h21/config/openai.env
# (see h21.service), written with: ~/data/sec/apikey write openai.h21.prod OPENAI_API_KEY <file>.
# The rest of the config is in ~/.local/share/h21/config/h21/config.toml, written with
# production defaults on the first deploy and never overwritten.
#
# H21_PORT is only for the health check, for when a drop-in moves the service to
# another port (e.g. a lab slot for a preview).
set -euo pipefail

revision="${1:-master}"
repository="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
home_directory="$HOME/.local/share/h21"
unit_directory="$HOME/.config/systemd/user"
config_file="$home_directory/config/h21/config.toml"
port="${H21_PORT:-8440}"
releases_to_keep=3

key_file="$home_directory/config/openai.env"
if [[ ! -f "$key_file" ]]; then
  echo "Missing $key_file. Write it with: ~/data/sec/apikey write openai.h21.prod OPENAI_API_KEY $key_file" >&2
  exit 1
fi

commit="$(git -C "$repository" rev-parse --verify "$revision^{commit}")"
release="$home_directory/releases/$commit"

if [[ ! -d "$release" ]]; then
  echo "Building release $commit"
  mkdir -p "$release"
  # A virtualenv hardcodes its own path, so the release is built in place and removed if the build fails.
  trap 'rm -rf "$release"' ERR
  git -C "$repository" archive "$commit" | tar -x -C "$release"
  (cd "$release" && uv sync --frozen --no-dev --quiet)
  trap - ERR
fi

mkdir -p "$unit_directory" "$home_directory/backups" "$home_directory/data/h21" "$(dirname "$config_file")"
if [[ ! -f "$config_file" ]]; then
  # The model and effort are the code defaults; only deployment settings go here.
  printf 'secure_cookies = true\n' > "$config_file"
  echo "Wrote $config_file"
fi

cp "$release"/deploy/h21.service "$release"/deploy/h21-backup.service "$release"/deploy/h21-backup.timer "$unit_directory/"
systemctl --user daemon-reload
systemctl --user enable --quiet h21.service h21-backup.timer
systemctl --user start h21-backup.timer

ln -sfn "$release" "$home_directory/current"
systemctl --user restart h21.service

for attempt in $(seq 1 40); do
  if curl --silent --output /dev/null "http://127.0.0.1:$port/login"; then
    echo "Live: $commit ($(git -C "$repository" log -1 --format=%s "$commit"))"
    break
  fi
  if [[ "$attempt" == 40 ]]; then
    echo "Release $commit did not come up. Check: journalctl --user -u h21.service" >&2
    exit 1
  fi
  sleep 0.5
done

# Prune old releases, never the live one.
ls -1t "$home_directory/releases" | tail -n "+$((releases_to_keep + 1))" | while read -r stale; do
  [[ "$home_directory/releases/$stale" != "$(readlink "$home_directory/current")" ]] && rm -rf "${home_directory:?}/releases/$stale"
done
