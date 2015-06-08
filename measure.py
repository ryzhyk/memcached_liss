import sys
from collections import Counter
import babeltrace
import statistics
import lttng
import os
import time
import datetime
import subprocess
import multiprocessing

from analyze       import *
from lttng_wrapper import *
from solve         import *

MAX_CALIBRATION_THREADS = multiprocessing.cpu_count()
NUM_CALIBRATION_CYCLES = 10000000

# extract number of cycles from calibration run
def dummy_c(col):
    timer = AvgCyclesBetween(lambda e: e.name == 'memcached:begin' and e['op'] == 'c' , 
                             lambda e: e.name == 'memcached:end' and e['op'] == 'c')

    for event in col.events:
        timer.push(event)
    return timer.summary()

def dummy_n(col):
    counter = AvgValue('memcached:contention', 'cnt')
    for event in col.events:
        counter.push(event)
    return counter.summary()

# extract number of cycles from calibration run
def calibrate_num_cycles(col):
#    contention = CountContentions(lambda e: e.name == 'memcached:calib_lock' , lambda e: e.name == 'memcached:calib_unlock')
    timer = AvgCyclesBetween(lambda e: e.name == 'memcached:start_calibrate_thread' , lambda e: e.name == 'memcached:end_calibrate_thread')

    for event in col.events:
#        if event.name == 'memcached:start_calibrate':
#            start_time = event.cycles
#        if event.name == 'memcached:end_calibrate':
#            end_time = event.cycles
#        contention.push(event)
        timer.push(event)
#    (uncont, cont, m) = contention.summary()
    return timer.summary()



def analyze_memcached(col):
    print("analyzing memcached trace")

    # create analyzers
    counter = AvgCyclesBetween(lambda e: e.name == 'memcached:lock_cache_req' , lambda e: e.name == 'memcached:unlock_cache_done')
    contention = CountContentions(lambda e: e.name == 'memcached:lock_cache_req' , lambda e: e.name == 'memcached:unlock_cache_done')
    analyzers = [counter, contention]

    for event in col.events:
        for a in analyzers:
            a.push(event)
#    for a in analyzers:
#        a.summary()

    # split trace into per-thread traces
#    traces = per_thread_traces(col)
    
    # serialize per-thread traces 
#    serialized = sum(traces.values(), [])
    #for event in serialized:
    #    print(format_event(event))

    (nsamples, avg, dev) = counter.summary()
    print('Average cycles between memcached:lock_cache_req and memcached:unlock_cache_done:', avg, ' std deviation:', dev)

    (uncont, cont, m) = contention.summary()
    print('Uncontended:', uncont, 'contended:', cont, 'mean contention:', m)

#    for tid in traces.keys():
#        print('Thread ', str(tid), ':', str(len(traces[tid])), " events")
#        print(*traces[tid], sep='\n')

# obtain per-thread traces
#def per_thread_traces(col):
#    d = dict()
#    i = 0
#    for event in col.events:
#        if event['pthread_id'] not in d:
#            print('new tid: ', event['pthread_id'])
#            d[event['pthread_id']] = []
#        evt_dict = dict(event.items())
#        evt_dict['name'] = event.name
#        d[event['pthread_id']].append(evt_dict)
#    return d

if __name__ == '__main__':
    l = dict()
    for i in range(1,MAX_CALIBRATION_THREADS+1):
        # calibration run with multiple threads
        res = lttng_session("calibrate", "./calibrate " + str(i) + " " + str(NUM_CALIBRATION_CYCLES), ['memcached:start_calibrate_thread', 'memcached:end_calibrate_thread'], calibrate_num_cycles)
        l[i] = res[1] / NUM_CALIBRATION_CYCLES
#        contended_cost = threadavg / NUM_CALIBRATION_CYCLES

#    interpolate_l (l)

    (dummy_c_samples, dummy_c_avg, dummy_c_dev) = lttng_session("dummy", "time ./dummy 4 c 100000 100 100", 
                                                               ['memcached:begin', 'memcached:end'], dummy_c)

    (dummy_c_fine_samples, dummy_c_fine_avg, dummy_c_fine_dev) = lttng_session("dummy", "time ./dummy 4 f 100000 100 100", 
                                                                              ['memcached:begin', 'memcached:end'], dummy_c)

    dummy_n_avg = lttng_session("dummy", "time ./dummy 4 c 100000 100 100", 
                                ['memcached:contention'], dummy_n)[1]

    dummy_n_fine_avg = lttng_session("dummy", "time ./dummy 4 f 100000 100 100", 
                                    ['memcached:contention'], dummy_n)[1]

    for i in range(1,MAX_CALIBRATION_THREADS+1):
        print ("l({0})={1}".format(i,l[i]))
    print ("c = {0} (std={1})".format (dummy_c_avg, dummy_c_dev))
    print ("c-c' = {0} (std={1})".format (dummy_c_fine_avg, dummy_c_fine_dev))
    print ("n = {0}".format (dummy_n_avg))
    print ("n' (measured) = {0}".format (dummy_n_fine_avg))

    nn = solve_nn (dummy_n_avg, dummy_c_avg, dummy_c_avg - dummy_c_fine_avg, l)
    
    print ("n' (predicted) = {0}".format (nn))

#    lttng_session("memcached", "./memcached -m 256 -p 11211 -t 8", analyze_memcached)
