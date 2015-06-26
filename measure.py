#! /usr/bin/python3

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
NUM_CALIBRATION_CYCLES = 10000
NUM_IDLE_CYCLES = 80000

NUM_DUMMY_RACING_CYCLES = 5000
NUM_DUMMY_INDEPENDENT_CYCLES = 5000

# extract number of cycles from calibration run
def measure_c(col):
    timer = AvgCyclesBetween(lambda e: e.name == 'memcached:c_end',
                             lambda e: e.name == 'memcached:c_begin', 
                             lambda e: e.name == 'memcached:c_end')
    counter = AvgValue('memcached:inside_cc', 'inside')
    counter_sections = AvgValue('memcached:c_end', 'num_sections')

    for event in col.events:
        timer.push(event)
        counter.push(event)
        counter_sections.push(event)
    (samples, c, c_dev) = timer.summary()
    cc = counter.summary()[1] * c
    sections = counter_sections.summary()[1]
    return (samples, c, cc, c_dev, sections)

def measure_n(col):
    counter = AvgValue('memcached:contention', 'cnt')
    for event in col.events:
        counter.push(event)
    return counter.summary()

#def calibrate_idle_cost(col):
##    contention = CountContentions(lambda e: e.name == 'memcached:calib_lock' , lambda e: e.name == 'memcached:calib_unlock')
#    timer = AvgCyclesBetween(lambda e: e.name == 'memcached:begin_idle' , lambda e: e.name == 'memcached:end_idle', lambda e: e.cycles)
#
#    for event in col.events:
#        timer.push(event)
#    return timer.summary()


def calibrate_contention(col):
    contention = CountContentions(lambda e: e.name == 'memcached:begin_idle' , lambda e: e.name == 'memcached:end_idle')
    for event in col.events:
        contention.push(event)
    return contention.summary()

# extract number of cycles from calibration run
def calibrate_num_cycles(col):
#    contention = CountContentions(lambda e: e.name == 'memcached:calib_lock' , lambda e: e.name == 'memcached:calib_unlock')
    timer = AvgCyclesBetween( lambda e: e.name == 'memcached:end_calibrate_thread'
                            , lambda e: e.name == 'memcached:start_calibrate_thread' 
                            , lambda e: e.name == 'memcached:end_calibrate_thread')

    for event in col.events:
#        if event.name == 'memcached:start_calibrate':
#            start_time = event.cycles
#        if event.name == 'memcached:end_calibrate':
#            end_time = event.cycles
#        contention.push(event)
        timer.push(event)
#    (uncont, cont, m) = contention.summary()
    return timer.summary()

def dummy_command(threads, locking):
    return "time ./dummy {0} {1} 10000 {2} {3}".format(threads, locking, NUM_DUMMY_RACING_CYCLES, NUM_DUMMY_INDEPENDENT_CYCLES)

def memcached_command(threads, locking):
    if locking == 'c':
        return "time ./memcached_c -t {0}".format(threads)
    else:
        return "time ./memcached_f -t {0}".format(threads)

def get_cpu_speed():
    proc = subprocess.Popen(["cat","/proc/cpuinfo"],
                             stdout=subprocess.PIPE)
    out, err = proc.communicate()

    for line in out.split("\n".encode('utf-8')):
        if "cpu MHz".encode('utf-8') in line:
            speed = float(line.split(":".encode('utf-8'))[1])
            break 

    return speed

def profile_locks(cmd):
    (c_samples, c, cc, c_dev, sections) = lttng_session( "profile_c"
                                                       , cmd(1, 'c')
                                                       , ['memcached:c_begin', 'memcached:c_end', 'memcached:inside_cc']
                                                       , measure_c)

    n = lttng_session( "profile_n"
                     , cmd(multiprocessing.cpu_count(),'c')
                     , ['memcached:contention']
                     , measure_n)[1]

    nn = lttng_session( "profile_contention"
                      , cmd(multiprocessing.cpu_count(),'f')
                      , ['memcached:contention']
                      , measure_n)[1]
    return((c,c_dev),cc,n,nn,sections)

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
        l[i] = ((res[1] / (NUM_CALIBRATION_CYCLES)) - idle_cost)
#        contended_cost = threadavg / NUM_CALIBRATION_CYCLES
#    l[3] = l[2]
#    l[4] = l[2]
    print("l: {0}".format(l))

    ll = interpolate_l(l)
#    ((c,c_dev),(cc,cc_dev),n,nn_measured) = profile_locks(dummy_command)
    ((c,c_dev),cc,n,nn_measured,sections) = profile_locks(memcached_command)

    for i in range(1,MAX_CALIBRATION_THREADS+1):
        print ("l({0})={1}".format(i,l[i]))
    print ("c = {0} (std={1})".format (c, c_dev))
    print ("c' = {0}".format (cc))
    print ("#crit sections = {0}".format (sections))
    print ("n = {0}".format (n))
    print ("n' (measured) = {0}".format (nn_measured))

    nn = solve_nn (n, c, cc, l, sections)
    
    print ("n' (predicted) = {0}".format (nn))

    cost_coarse = n * (c + ll(n))
    cost_fine   = nn * (cc + sections * ll(nn)) + (c-cc)

    print ("estimated cost of coarse-grained locking: {0}".format(cost_coarse))
    print ("estimated cost of fine-grained locking: {0}".format(cost_fine))
    print ("speed-up with fine-grained locking:: {0}".format(cost_coarse/cost_fine))
