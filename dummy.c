#define _GNU_SOURCE

#include <pthread.h>
#include <stdio.h>
#include <memcached_prof.h>
#include <stdatomic.h>

#define yield() {}

atomic_ushort contention_counter = 0;

long ncontended;
long nfalse;
long niter;
pthread_mutex_t l;
int coarse;

volatile long v;

static void work1() {
    int i;
    for (i = 0; i < 10; i++, v++);
}

static void work2() {
    int i;
    volatile int u = 0;
    for (i = 0; i < 10; i++, u++);
}

static void lock () {
    atomic_fetch_add(&contention_counter, 1);
/*    tracepoint(memcached, lock);*/
    pthread_mutex_lock(&l);
}

static void unlock () {
    pthread_mutex_unlock(&l);
    atomic_fetch_sub(&contention_counter, 1);
/*    tracepoint(memcached, unlock);*/
}

long ndelay = 1000;

static void delay () {
    long i;
    for (i = 0; i < ndelay; i++, work2());
}

static void shared1 () {
    long i;
    for (i = 0; i < ncontended; i++, work1());
    yield();
}

static void shared2 () {
    shared1();
}

static void shared3 () {
    shared1();
}

static void local () {
    long i;
    for (i = 0; i < nfalse; i++, work2());
}

static void* worker_thread_coarse(void*arg) {
    long j;
    for (j = 0; j < niter; j++) {
        lock();

        shared1();
        shared2();
        local();
        shared3();
        
        unlock();
    };
}

static void* worker_thread_fine(void*arg) {
    long j;
    for (j = 0; j < niter; j++) {
        lock();
        shared1();
        unlock();
        
        lock();
        shared2();
        unlock();

        local();
        
        lock();
        shared3();
        unlock();
    };
}

static void* worker_thread_finer1(void*arg) {
    long j;
    for (j = 0; j < niter; j++) {
        lock();
        shared1();
        unlock();
        
        lock();
        shared2();
        local();
        shared3();
        unlock();
    };
}

static void* worker_thread_finer2(void*arg) {
    long j;
    for (j = 0; j < niter; j++) {
        lock();
        shared1();
        shared2();
        unlock();

        local();

        lock();
        shared3();
        unlock();
    };
}

//static void* worker_thread_fine(void*arg) {
//    long j;
//    for (j = 0; j < niter; j++) {
//        lock();
//        tracepoint(memcached, c_begin);
//        tracepoint(memcached, cc_begin);
//        shared1();
//        tracepoint(memcached, cc_end);
//        tracepoint(memcached, contention, atomic_load(&contention_counter));
//        unlock();
//
//        local();
//
//        lock();
//        tracepoint(memcached, cc_begin);
//        shared3();
//        tracepoint(memcached, cc_end);
//        tracepoint(memcached, c_end, 2);
//        unlock();
//
///*        for (i = 0; i < nfalse; i++, work2());*/
//    };
//    pthread_exit(NULL);
//}

static void usage(char* argv[]) {
    fprintf(stderr, "usage: %s <num_threads> [f|1|2|c] <num_iterations> <num_racing_cycles> <num_independent_cycles>\n", argv[0]);
}

int main(int argc, char* argv[]) {
    int i;
    int rc;
    pthread_t * threads;
    int nthreads;
    cpu_set_t cpuset;
    char* locking;
    void* (*tfunc)(void*); 

    if (argc != 6) {
        usage(argv);
        exit(-1);
    };

    nthreads   = atoi(argv[1]);
    if (*argv[2] == 'c') {
        tfunc = worker_thread_coarse;
        locking = "coarse-grained";
    } else if (*argv[2] == 'f') {
        tfunc = worker_thread_fine;
        locking = "fine-grained";
    } else if (*argv[2] == '1') {
        tfunc = worker_thread_finer1;
        locking = "finer 1";
    } else if (*argv[2] == '2') {
        tfunc = worker_thread_finer2;
        locking = "finer 2";
    } else {
        usage(argv);
        exit(-1);
    };
    niter      = atoi(argv[3]);
    ncontended = atoi(argv[4]);
    nfalse     = atoi(argv[5]);
    printf("Test run with %i threads, %s locking, %ld iterations, %ld racing cycles, %ld independent cycles\n", 
                            nthreads, locking   , niter        , ncontended      , nfalse);

    threads = (pthread_t*) calloc(nthreads, sizeof(pthread_t));
    pthread_mutex_init(&l, NULL);

    tracepoint(memcached, begin, "dummy_run");
    for (i = 0; i < nthreads; i++) {
        rc = pthread_create(&threads[i], NULL, tfunc, (void *)NULL);
        if (rc){
            fprintf(stderr, "ERROR; return code from pthread_create() is %d\n", rc);
            exit(-1);
        };
        CPU_ZERO(&cpuset);
        CPU_SET(i, &cpuset); 
        rc = pthread_setaffinity_np(threads[i], sizeof(cpu_set_t), &cpuset);
        if (rc){
            fprintf(stderr, "ERROR; return code from pthread_setaffinity_np(%i) is %d\n", i, rc);
            exit(-1);
        };
    };
    for (i = 0; i < nthreads; i++) {
        rc = pthread_join(threads[i], NULL);
        if (rc) {
            fprintf(stderr, "ERROR; return code from pthread_join(%i) is %d\n", i, rc);
            exit(-1);
        };
    };
    tracepoint(memcached, end, "dummy_run");
    free(threads);
    return 0;
}
