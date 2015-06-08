import lttng
import babeltrace
import datetime
import time
import os
import subprocess

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


