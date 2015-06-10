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
NUM_CALIBRATION_CYCLES = 20000
NUM_IDLE_CYCLES = 40000

NUM_DUMMY_RACING_CYCLES = 500
NUM_DUMMY_INDEPENDENT_CYCLES = 5000

# extract number of cycles from calibration run
def dummy_c(col):
    timer = AvgCyclesBetween(lambda e: e.name == 'memcached:begin' and e['op'] == 'c' , 
                             lambda e: e.name == 'memcached:end' and e['op'] == 'c' ,
                             lambda e: e.cycles)

    for event in col.events:
        timer.push(event)
    return timer.summary()

def dummy_n(col):
    counter = AvgValue('memcached:contention', 'cnt')
    for event in col.events:
        counter.push(event)
    return counter.summary()

def calibrate_idle_cost(col):
#    contention = CountContentions(lambda e: e.name == 'memcached:calib_lock' , lambda e: e.name == 'memcached:calib_unlock')
    timer = AvgCyclesBetween(lambda e: e.name == 'memcached:begin_idle' , lambda e: e.name == 'memcached:end_idle', lambda e: e.cycles)

    for event in col.events:
        timer.push(event)
    return timer.summary()


def calibrate_contention(col):
    contention = CountContentions(lambda e: e.name == 'memcached:begin_idle' , lambda e: e.name == 'memcached:end_idle')
    for event in col.events:
        contention.push(event)
    return contention.summary()

# extract number of cycles from calibration run
def calibrate_num_cycles(col):
#    contention = CountContentions(lambda e: e.name == 'memcached:calib_lock' , lambda e: e.name == 'memcached:calib_unlock')
    timer = AvgCyclesBetween(lambda e: e.name == 'memcached:start_calibrate_thread' , lambda e: e.name == 'memcached:end_calibrate_thread', lambda e: e.cycles)

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

def dummy_command(threads, locking):
    return "time ./dummy {0} {1} 100000 {2} {3}".format(threads, locking, NUM_DUMMY_RACING_CYCLES, NUM_DUMMY_INDEPENDENT_CYCLES)

def get_cpu_speed():
    proc = subprocess.Popen(["cat","/proc/cpuinfo"],
                             stdout=subprocess.PIPE)
    out, err = proc.communicate()

    for line in out.split("\n".encode('utf-8')):
        if "cpu MHz".encode('utf-8') in line:
            speed = float(line.split(":".encode('utf-8'))[1])
            break 

    return speed


if __name__ == '__main__':
    l = dict()
    #cpu_ghz = get_cpu_speed() / 1000
    idle = lttng_session("calibrate", "time ./calibrate a 1" + " " + str(NUM_CALIBRATION_CYCLES) + " " + str(NUM_IDLE_CYCLES), 
                         ['memcached:start_calibrate_thread', 'memcached:end_calibrate_thread'], calibrate_num_cycles)
    idle_cost = idle[1] / NUM_CALIBRATION_CYCLES
    print ("idle calibration cycle estimate: {0}".format(idle_cost))
    for i in range(1,MAX_CALIBRATION_THREADS+1):
        # calibration run with multiple threads
        res = lttng_session("calibrate", "time ./calibrate s " + str(i) + " " + str(NUM_CALIBRATION_CYCLES) + " " + str(NUM_IDLE_CYCLES),
                            ['memcached:start_calibrate_thread', 'memcached:end_calibrate_thread'], calibrate_num_cycles)
        l[i] = ((res[1] / (i * NUM_CALIBRATION_CYCLES)) - idle_cost)
#        contended_cost = threadavg / NUM_CALIBRATION_CYCLES
#    l[3] = l[2]
#    l[4] = l[2]
    print("l: {0}".format(l))

    ll = interpolate_l(l)

    (dummy_c_samples, c, dummy_c_dev) = lttng_session("dummy", dummy_command(1, 'c'), 
                                                      ['memcached:begin', 'memcached:end'], dummy_c)

    (dummy_c_fine_samples, cc05, dummy_c_fine_dev) = lttng_session("dummy", dummy_command(1, 'f'), 
                                                                               ['memcached:begin', 'memcached:end'], dummy_c)

    n = lttng_session("dummy", dummy_command(multiprocessing.cpu_count(),'c'), 
                      ['memcached:contention'], dummy_n)[1]

    dummy_n_fine_avg = lttng_session("dummy", dummy_command(multiprocessing.cpu_count(),'f'), 
                                    ['memcached:contention'], dummy_n)[1]

    cc = cc05 * 2

    for i in range(1,MAX_CALIBRATION_THREADS+1):
        print ("l({0})={1}".format(i,l[i]))
    print ("c = {0} (std={1})".format (c, dummy_c_dev))
    print ("c' = {0} (std={1})".format (cc, dummy_c_fine_dev))
    print ("n = {0}".format (n))
    print ("n' (measured) = {0}".format (dummy_n_fine_avg))


    nn = solve_nn (n, c, cc, l)
    
    print ("n' (predicted) = {0}".format (nn))

    cost_coarse = n * c + ll(n)
    cost_fine   = cc * nn + (c-cc) + 2 * ll(nn)

    print ("estimated cost of coarse-grained locking: {0}".format(cost_coarse))
    print ("estimated cost of fine-grained locking: {0}".format(cost_fine))
    print ("speed-up with fine-grained locking:: {0}".format(cost_coarse/cost_fine))

#    lttng_session("memcached", "./memcached -m 256 -p 11211 -t 8", analyze_memcached)
