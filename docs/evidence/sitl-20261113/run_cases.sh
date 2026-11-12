#!/bin/bash
# usage: run_cases.sh <duration_s> <tag> <case:instance[:name[:extra~args]]> ...   (extra args use ~ for spaces)
source ~/venv-ap/bin/activate
S=/mnt/d/AgentWork/ERDI/upgrade-r4-20261113/W3a-repos/sitl/erdi_sitl_case.py
OUT=/mnt/d/AgentWork/ERDI/upgrade-r4-20261113/W3a-repos/sitl/out
DUR=$1; TAG=$2; shift 2
mkdir -p $OUT
NAMES=()
for spec in "$@"; do
  IFS=: read c i n x <<< "$spec"; n=${n:-$c}; x=${x//\~/ }
  NAMES+=("$n")
  timeout $((DUR+300)) python3 $S --case $c --instance $i --duration $DUR $x --out /tmp/erdi-w3a/$TAG-$n > /tmp/$TAG-$n.out 2>&1 &
done
if [ -n "$CHECKPOINT" ]; then
  # periodic copy so a killed run still leaves partial logs
  ( while sleep 300; do for n in "${NAMES[@]}"; do mkdir -p $OUT/$TAG-$n; cp /tmp/erdi-w3a/$TAG-$n/sitl.log $OUT/$TAG-$n/sitl.partial.log 2>/dev/null; done; done ) &
  CP=$!
fi
wait $(jobs -p | grep -v "^${CP:-x}$") 2>/dev/null
[ -n "$CP" ] && kill $CP 2>/dev/null
for n in "${NAMES[@]}"; do mkdir -p $OUT/$TAG-$n; cp /tmp/erdi-w3a/$TAG-$n/{summary.json,statustext.log,distance_sensor.csv,rangefinder.csv,erdi.parm} $OUT/$TAG-$n/ 2>/dev/null; cp /tmp/$TAG-$n.out $OUT/$TAG-$n/run.out; tail -n 200 /tmp/erdi-w3a/$TAG-$n/sitl.log > $OUT/$TAG-$n/sitl.tail.log; done
