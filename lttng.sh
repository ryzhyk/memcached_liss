#!/bin/bash

lttng create memcached
lttng enable-event -u 'memcached:*'
lttng add-context -u -t perf:thread:cpu-cycles -t pthread_id
lttng start
./memcached -m 256 -p 11211 -t 4
lttng stop
lttng destroy memcached
