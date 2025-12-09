#!/bin/bash
# cpu_freq_logger.sh

OUTFILE=$1
INTERVAL=$2

# Check that both arguments are provided
if [[ -z "$OUTFILE" || -z "$INTERVAL" ]]; then
    echo "Usage: $0 <output_file> <interval_seconds>"
    exit 1
fi

rm -f $OUTFILE

nohup bash -c "
while true; do
    TS=\$(date +\"%Y-%m-%d_%H:%M:%S\")
    FREQ=\$(
    for cpu in /sys/devices/system/cpu/cpu*/cpufreq; do
        if [[ -f \"\$cpu/cpuinfo_cur_freq\" ]]; then
            echo \"\$cpu/cpuinfo_cur_freq\"
        else
            echo \"\$cpu/scaling_cur_freq\"
        fi
    done | sort -V | xargs cat | tr '\n' ' '
    )
    echo \"\$TS \$FREQ\" >> \"$OUTFILE\"
    sleep \"$INTERVAL\"
done
" >/dev/null 2>&1 &

echo "Started logging CPU frequencies in $OUTFILE"
