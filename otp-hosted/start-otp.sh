#!/usr/bin/env bash
set -Eeuo pipefail
DATA_DIR=/var/opentripplanner
mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

# Render must mount a persistent disk here for production. Graph build requires
# several GB of RAM and is intentionally performed only when graph.obj is absent.
if [[ ! -s graph.obj ]]; then
  echo 'No OTP graph found; preparing Merseyside inputs.'
  curl --fail --location --retry 3 --connect-timeout 20 --max-time 900 \
    'https://download.geofabrik.de/europe/united-kingdom/england/merseyside-latest.osm.pbf' \
    --output merseyside-latest.osm.pbf
  curl --fail --location --retry 3 --connect-timeout 20 --max-time 900 \
    'https://storage.travelwhiz.app/generated-gtfs/uk-busmetro-NW.gtfs.zip' \
    --output uk-busmetro-NW.gtfs.zip
  curl --fail --location --retry 3 --connect-timeout 20 --max-time 900 \
    'https://storage.travelwhiz.app/generated-gtfs/gb-nationalrail.gtfs.zip' \
    --output gb-nationalrail.gtfs.zip
  echo 'Building OTP graph. This needs a persistent disk and several GB of RAM.'
  /__cacert_entrypoint.sh --build --save
fi

if [[ ! -s graph.obj ]]; then
  echo 'OTP graph build did not produce graph.obj; refusing to start an empty planner.' >&2
  exit 1
fi

exec /__cacert_entrypoint.sh --load --serve --port "${PORT:-8080}"
