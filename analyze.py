import babeltrace
import statistics

def format_event(event):
    op = event.get('op', '-')
    return "{0}: {1}: tid={2}, op={3}".format(event.cycles, event.name.ljust(30), event['pthread_id'], op)
    
# Average value of a counter
class AvgValue:
    def __init__(self, event_name, cnt_name):
        self.samples = list()
        self.event_name = event_name
        self.cnt_name = cnt_name

    def push(self, event):
        if self.event_name == event.name:
            self.samples.append(event[self.cnt_name])

    def summary(self):
#        print ("samples:", self.samples)
        if len(self.samples) == 0:
            return 0.0        
        else:
            m = statistics.mean(self.samples)
            if len(self.samples) >= 2:
                d = statistics.stdev(self.samples, m)
            else:
                d = 0.0
            return (len(self.samples), m, d)


# find average time between two events in the same thread
class AvgCyclesBetween:
    def __init__(self, reset_filter, start_filter, end_filter, ts = lambda e: e['perf_thread_cycles']):
        self.samples = list()
        self.perthread = dict()
        self.start_filter = start_filter
        self.end_filter = end_filter
        self.reset_filter = reset_filter
        self.ts_function = ts

    def push(self, event):
        tid = event['pthread_id']
        if self.start_filter(event):
            if tid not in self.perthread: self.perthread[tid] = (False, 0, 0)
#            print('start event')
#            print(format_event(event))
            assert not self.perthread[tid][0]
            self.perthread[tid] = (True, self.ts_function(event), self.perthread[tid][2])
        if self.end_filter(event):
            if tid not in self.perthread: self.perthread[tid] = (False, 0, 0)
#            print('end event')
#            print(format_event(event))
            assert self.perthread[tid][0]
            cycles = self.ts_function(event) - self.perthread[tid][1]
            self.perthread[tid] = (False, 0, self.perthread[tid][2] + cycles)
#            print('sample: ', cycles)

        if self.reset_filter(event):
            if tid not in self.perthread: self.perthread[tid] = (False, 0, 0)
            self.samples.append(self.perthread[tid][2])
            self.perthread[tid] = (False, 0, 0)


    def summary(self):
#        print ("#of threads:", len(self.perthread.keys()))
#        print ("samples:", self.samples)
        
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


