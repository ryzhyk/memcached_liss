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
    counter = AvgValue(lambda e: e.name == 'memcached:inside_cc', lambda e: e['inside'])
    counter_sections = AvgValue(lambda e: e.name == 'memcached:c_end', lambda e: e['num_sections'])

    for event in col.events:
        timer.push(event)
        counter.push(event)
        counter_sections.push(event)
    (samples, c, c_dev) = timer.summary()
    cc = counter.summary()[1] * c
    sections = counter_sections.summary()[1]
    return (samples, c, cc, c_dev, sections)

def measure_n(col):
    counter = AvgValue(lambda e: e.name == 'memcached:contention', lambda e: e['cnt'])
    for event in col.events:
        counter.push(event)
    return counter.summary()

def measure_blocks(col):
    counters = Count(lambda e: e.name == 'memcached:block_id', lambda e: e['id'])
    for event in col.events:
        counters.push(event)
    return counters.summary()

max_nblks = 10

def count_blocks(col):
    counters = dict()
    for i in range(0,max_nblks):
        counters[i] = AvgValue(lambda e: e.name == 'memcached:blk_cnts', lambda e: e['cnts'][i] if (len(e['cnts'])>i) else 0)
    for event in col.events:
        for i in range(0,max_nblks):
            counters[i].push(event)

#    for i in range(0,max_nblks):
#        print ("samples{0}: {1}".format(i,counters[i].samples))

    return {k: (cnt.summary()[1]) for k, cnt in counters.items()}

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

def dummy_command(threads, locking, iterations = 10000):
    return "time ./dummy {0} {1} {2} {3} {4}".format(threads, locking, iterations, NUM_DUMMY_RACING_CYCLES, NUM_DUMMY_INDEPENDENT_CYCLES)

def memcached_command(threads, locking, iterations = 50000):
    if locking == 'c':
        return "time ./memcached_c -t {0} -N {1} -j{2}".format(threads, iterations, item_size)
    else:
        return "time ./memcached_f -t {0} -N {1} -j{2}".format(threads, iterations, item_size)

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

    (nsamples, blk_samples) = lttng_session( "profile_block_costs"
                                           , cmd(1,'c')
                                           , ['memcached:block_id']
                                           , measure_blocks)


    blk_cnts = lttng_session( "profile_block_counts"
                            , cmd(1,'c')
                            , ['memcached:blk_cnts']
                            , count_blocks)
    
    blk_costs = {k: ((blk_samples[k] * c / nsamples), v) for k, v in blk_cnts.items() if k in blk_samples}

    nn = lttng_session( "profile_contention"
                      , cmd(multiprocessing.cpu_count(),'f')
                      , ['memcached:contention']
                      , measure_n)[1]
    return((c,c_dev),cc,n,nn,sections,blk_costs)

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

    for item_size in {2 ** i for i in range(10,20)}:
        ((c,c_dev),cc,n,nn_measured,sections,blk_costs) = profile_locks(memcached_command)

        for i in range(1,MAX_CALIBRATION_THREADS+1):
            print ("l({0})={1}".format(i,l[i]))
        print ("c = {0} (std={1})".format (c, c_dev))
        print ("c' = {0}".format (cc))
        print ("#crit sections = {0}".format (sections))
        print ("n' (measured) = {0}".format (nn_measured))

        report = ''
        for k, (cost, cnt) in blk_costs.items():
            report += "BLOCK_PROF_DATA: block{0} {1} {2}\n".format(k,cost,cnt)

        report += '\n'
        report += "GLOBAL_PROF_DATA: n {0}\n".format (n)
        report += "GLOBAL_PROF_DATA: c {0}\n".format (c)
        for i in range(1,MAX_CALIBRATION_THREADS+1):
            report += "GLOBAL_PROF_DATA: l_map {0} {1}\n".format(i,l[i])
        report += '\n'
        report += "ESTIMATED_DATA: N_bound 4\n"

        print(report)
    
        f = open("report{0}".format(item_size), 'w')
        f.write(report)
        f.close

#    print ("blk_costs: {0}".format (blk_costs))

# The following requires directly measuring c'
#    nn = solve_nn (n, c, cc, l, sections)
#    
#    print ("n' (predicted) = {0}".format (nn))
#
#    cost_coarse = n * (c + ll(n))
#    cost_fine   = nn * (cc + sections * ll(nn)) + (c-cc)
#
#    print ("estimated cost of coarse-grained locking: {0}".format(cost_coarse))
#    print ("estimated cost of fine-grained locking: {0}".format(cost_fine))
#    print ("speed-up with fine-grained locking:: {0}".format(cost_coarse/cost_fine))
