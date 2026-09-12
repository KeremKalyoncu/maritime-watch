#!/usr/bin/env bash
# Maritime Watch Turkiye - 7/24 Canli Izleme & Bot Servisi
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "========================================================"
echo " Maritime Watch Türkiye - 7/24 Canlı İzleme & Bot Servisi"
echo "========================================================"
python3 run.py --loop --send
