#!/bin/bash

lttng create memcached
lttng enable-event -u 'memcached:*'
lttng add-context -u -t perf:thread:cpu-cycles -t pthread_id
str=$(lttng list memcached | sed -n 2p)
dir=${str:16}
lttng start
./memcached -m 256 -p 11211 -t 8
lttng stop
lttng destroy memcached
python3 analyze_trace.py $dir/ust/uid/$UID/$(getconf LONG_BIT)-bit/
