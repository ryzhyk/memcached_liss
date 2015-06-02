#!/bin/bash

lttng create memcached
lttng enable-event -u 'memcached:*'
lttng start
./memcached -m 256 -p 11211 -t 4
lttng stop
lttng destroy memcached
