#!/bin/bash
# Find and delete score JSONs whose answer markdown is a runner-error
# placeholder (ModuleNotFoundError, runner crash). After fixing the missing
# modules, those pairs need to be re-run.
DIR=/opt/deep_reserch/data/results/deep_v3
REPORT_DIR=/opt/deep_reserch/data/results/deep
removed=0
kept=0
for sj in "$DIR"/*_matrix.score.json; do
    [ ! -f "$sj" ] && continue
    base=$(basename "$sj" .score.json)
    md="$REPORT_DIR/${base}.md"
    if [ -f "$md" ]; then
        head=$(head -c 200 "$md" 2>/dev/null)
        if echo "$head" | grep -qE '\(runner error:|ModuleNotFoundError|produced no report after [0-9]+s, exit=' ; then
            echo "REMOVING: $base"
            rm -f "$sj"
            removed=$((removed + 1))
        else
            kept=$((kept + 1))
        fi
    fi
done
echo
echo "removed: $removed score JSONs (will be re-run)"
echo "kept   : $kept score JSONs (real answers)"
echo "total remaining: $(ls "$DIR"/*_matrix.score.json 2>/dev/null | wc -l)"
