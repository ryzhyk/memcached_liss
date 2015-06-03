import sys
from collections import Counter
import babeltrace
import statistics

# find average time between two events in the same thread
class AvgCyclesBetween:
    samples = list()
    perthread = dict()

    def __init__(self, start_filter, end_filter):
        self.start_filter = start_filter
        self.end_filter = end_filter

    def push(self, event):
        tid = event['pthread_id']
        if tid not in self.perthread:
            self.perthread[tid] = (False, 0)
        if self.start_filter(event):
#            print('start event')
#            print(format_event(event))
            assert not self.perthread[tid][0]
            self.perthread[tid] = (True, event['perf_thread_cpu_cycles'])
        if self.end_filter(event):
#            print('end event')
#            print(format_event(event))
            assert self.perthread[tid][0]
            cycles = event['perf_thread_cpu_cycles'] - self.perthread[tid][1]
            self.perthread[tid] = (False, 0)
            self.samples.append(cycles);
#            print('sample: ', cycles)

    def summary(self):
        print ("#of threads:", len(self.perthread.keys()))
        if len(self.samples) == 0:
            return (0,0.0,0.0)        
        else:
            m = statistics.mean(self.samples)
            d = statistics.stdev(self.samples, m)
            return (len(self.samples), m, d)

# measure the number of contended and uncontended lock acquisitions
class CountContentions:
    perthread = dict()
    samples = []
    occupants = 0
    contended = 0
    uncontended = 0

    def __init__(self, start_filter, end_filter):
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
        return (self.uncontended, self.contended, statistics.mean(self.samples))


# measure contention over a section marked by a pair of events

def analyze():
    if len(sys.argv) != 2:
        msg = 'Usage: python {} TRACEPATH'.format(sys.argv[0])
        raise ValueError(msg)

    # a trace collection holds one to many traces
    col = babeltrace.TraceCollection()

    # add the trace provided by the user
    # (LTTng traces always have the 'ctf' format)
    if col.add_trace(sys.argv[1], 'ctf') is None:
        raise RuntimeError('Cannot add trace')

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
    return "{0}: {1}: tid={2}, op={3}".format(event['perf_thread_cpu_cycles'], event.name.ljust(30), event['pthread_id'], event['op'])
    

if __name__ == '__main__':
    analyze()

