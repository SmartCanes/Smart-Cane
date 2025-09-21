#!/bin/sh
set -e

GRAPH_DIR="/app/graph-cache"

if [ ! -d "$GRAPH_DIR" ] || [ -z "$(ls -A $GRAPH_DIR)" ]; then
    echo "Graph cache not found. Importing map..."
    java -Xmx2g -jar graphhopper.jar import config.yml
else
    echo "Graph cache already exists. Skipping import."
fi

echo "Starting GraphHopper server..."
java -Xmx2g -jar graphhopper.jar server config.yml
