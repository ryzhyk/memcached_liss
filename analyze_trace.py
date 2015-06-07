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

MAX_CALIBRATION_THREADS = multiprocessing.cpu_count()
NUM_CALIBRATION_CYCLES = 10000000

# find average time between two events in the same thread
class AvgCyclesBetween:
    def __init__(self, start_filter, end_filter):
        self.samples = list()
        self.perthread = dict()
        self.start_filter = start_filter
        self.end_filter = end_filter

    def push(self, event):
        tid = event['pthread_id']
        if self.start_filter(event):
            if tid not in self.perthread: self.perthread[tid] = (False, 0)
#            print('start event')
#            print(format_event(event))
            assert not self.perthread[tid][0]
            self.perthread[tid] = (True, event['perf_thread_cpu_cycles'])
        if self.end_filter(event):
            if tid not in self.perthread: self.perthread[tid] = (False, 0)
#            print('end event')
#            print(format_event(event))
            assert self.perthread[tid][0]
            cycles = event['perf_thread_cpu_cycles'] - self.perthread[tid][1]
            self.perthread[tid] = (False, 0)
            self.samples.append(cycles);
#            print('sample: ', cycles)

    def summary(self):
        print ("#of threads:", len(self.perthread.keys()))
        print ("samples:", self.samples)
        
        if len(self.samples) == 0:
            return (0,0.0,0.0)        
        else:
            m = statistics.mean(self.samples)
            if len(self.samples) >= 2:
                d = statistics.stdev(self.samples, m)
            else:
                d = 0
            return (len(self.samples), m, d)

# measure the number of contended and uncontended lock acquisitions
class CountContentions:
    def __init__(self, start_filter, end_filter):
        self.perthread = dict()
        self.samples = []
        self.occupants = 0
        self.contended = 0
        self.uncontended = 0
        self.start_filter = start_filter
        self.end_filter = end_filter

    def push(self, event):
        tid = event['pthread_id']
        if tid not in self.perthread:
            self.perthread[tid] = False
        if self.start_filter(event):
#            print('start event')
#            print(format_event(event))
            assert not self.perthread[tid]
            if self.occupants == 0:
                self.uncontended = self.uncontended + 1
            else:
                self.contended = self.contended + 1
            self.occupants = self.occupants + 1 
            self.samples.append(self.occupants)
            self.perthread[tid] = True
        if self.end_filter(event):
#            print('end event')
#            print(format_event(event))
            assert self.perthread[tid]
            assert self.occupants > 0
            self.perthread[tid] = False
            self.occupants = self.occupants - 1

    def summary(self):
        if len(self.samples) > 0:
            return (self.uncontended, self.contended, statistics.mean(self.samples))
        else:
            return (self.uncontended, self.contended, 1)


# extract number of cycles from calibration run
def dummy_c(col):
    timer = AvgCyclesBetween(lambda e: e.name == 'memcached:begin' and e['op'] == 'c' , 
                             lambda e: e.name == 'memcached:end' and e['op'] == 'c')

    for event in col.events:
        timer.push(event)
    return timer.summary()

def dummy_n(col):
    counter = CountContentions(lambda e: e.name == 'memcached:lock', 
                               lambda e: e.name == 'memcached:unlock')
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

def format_event(event):
    op = event.get('op', '-')
    return "{0}: {1}: tid={2}, op={3}".format(event.cycles, event.name.ljust(30), event['pthread_id'], op)
    

def lttng_session(session_name, command, names, analyzer):
    ts = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d-%H-%M-%S-%f')
    tracedir = os.environ['HOME'] + "/lttng-traces/" + session_name + "-" + ts
    print('Writing trace to ' + tracedir)
    lttng.destroy(session_name)
    res = lttng.create(session_name, tracedir)
    if res<0:
        raise Exception("Failed to create lttng session")

    dom = lttng.Domain()
    dom.type = lttng.DOMAIN_UST

    han = None
    han = lttng.Handle(session_name, dom)
    if han is None:
        raise Exception("Handle not created")

    channel = lttng.Channel()
    channel.name = "channel0"
    channel.attr.overwrite = 0
    channel.attr.subbuf_size = 1048576
    channel.attr.num_subbuf = 8
    channel.attr.switch_timer_interval = 0
    channel.attr.read_timer_interval = 0
    channel.attr.output = lttng.EVENT_MMAP

    res = lttng.enable_channel(han, channel)
    if res<0:
        raise Exception("Failed to enable channel")
    
    for n in names:
        # lttng enable-event -u 'memcached:*'
        event = lttng.Event()
        event.type = lttng.EVENT_TRACEPOINT
        event.name = n
        lttng.enable_event(han, event, "channel0")

    os.system("lttng add-context -s" + session_name + " -u -t perf:thread:cpu-cycles -t pthread_id")

#    ctx = lttng.EventContext()
#    ctx.type = EVENT_CONTEXT_PTHREAD_ID
#    res = lttng.add_context(han, ctx, None, None)
#    assert res >= 0  
#
#    ctx.type = EVENT_CONTEXT_PERF_COUNTER
#    ctx.u.perf_counter.name = "cpu-cycles"
#    res = lttng.add_context(han, ctx, None, None)
#    assert res >= 0  

    lttng.start(session_name)

    print("running ", command)
    os.system(command)

    lttng.stop(session_name)
    lttng.destroy(session_name)
    
    subdir = subprocess.check_output(['ls', tracedir+'/ust/pid/']).decode("utf-8").rstrip()

    babeldir = tracedir+'/ust/pid/'+subdir
    print("analyzing trace in", babeldir)

    col = babeltrace.TraceCollection()
    if col.add_trace(babeldir, 'ctf') is None:
        raise RuntimeError('Cannot add trace')
    return analyzer(col)

if __name__ == '__main__':
    l = dict()
    for i in range(1,MAX_CALIBRATION_THREADS+1):
        # calibration run with multiple threads
        res = lttng_session("calibrate", "./calibrate " + str(i) + " " + str(NUM_CALIBRATION_CYCLES), ['memcached:start_calibrate_thread', 'memcached:end_calibrate_thread'], calibrate_num_cycles)
        l[i] = res[1] / NUM_CALIBRATION_CYCLES
#        contended_cost = threadavg / NUM_CALIBRATION_CYCLES

    (dummy_c_samples, dummy_c_avg, dummy_c_dev) = lttng_session("dummy", "time ./dummy 4 c 50000 100 100", 
                                                               ['memcached:begin', 'memcached:end'], dummy_c)

    (dummy_c_fine_samples, dummy_c_fine_avg, dummy_c_fine_dev) = lttng_session("dummy", "time ./dummy 4 f 50000 100 100", 
                                                                              ['memcached:begin', 'memcached:end'], dummy_c)

    dummy_n_avg = lttng_session("dummy", "time ./dummy 4 c 50000 100 100", 
                                ['memcached:lock', 'memcached:unlock'], dummy_n)[2]

    dummy_n_fine_avg = lttng_session("dummy", "time ./dummy 4 f 50000 100 100", 
                                    ['memcached:lock', 'memcached:unlock'], dummy_n)[2]

    for i in range(1,MAX_CALIBRATION_THREADS+1):
        print ("l({0})={1}".format(i,l[i]))
    print ("c = {0} (std={1})".format (dummy_c_avg, dummy_c_dev))
    print ("c-c' = {0} (std={1})".format (dummy_c_fine_avg, dummy_c_fine_dev))
    print ("n = {0}".format (dummy_n_avg))
    print ("n' = {0}".format (dummy_n_fine_avg))


#    lttng_session("memcached", "./memcached -m 256 -p 11211 -t 8", analyze_memcached)
