#define _GNU_SOURCE

#include <pthread.h>
#include <stdio.h>
#include <memcached_prof.h>

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
    tracepoint(memcached, lock);
    pthread_mutex_lock(&l);
}

static void unlock () {
    pthread_mutex_unlock(&l);
    tracepoint(memcached, unlock);
}

static void* worker_thread_coarse(void*arg) {
    long i;
    long j;
    for (j = 0; j < niter; j++) {
        lock();
        tracepoint(memcached, begin, "c");
        for (i = 0; i < ncontended; i++, work1());
        for (i = 0; i < nfalse; i++, work2());
        for (i = 0; i < ncontended; i++, work1());
        tracepoint(memcached, end, "c");
        unlock();
    };
    pthread_exit(NULL);
}

static void* worker_thread_fine(void*arg) {
    long i;
    long j;
    for (j = 0; j < niter; j++) {
        lock();
        for (i = 0; i < ncontended; i++, work1());
        unlock();

        tracepoint(memcached, begin, "c");
        for (i = 0; i < nfalse; i++, work2());
        tracepoint(memcached, end, "c");

        lock();
        for (i = 0; i < ncontended; i++, work1());
        unlock();
    };
    pthread_exit(NULL);
}

static void usage(char* argv[]) {
    fprintf(stderr, "usage: %s <num_threads> [c|f] <num_iterations> <num_racing_cycles> <num_independent_cycles>\n", argv[0]);
}

int main(int argc, char* argv[]) {
    int i;
    int rc;
    pthread_t * threads;
    int nthreads;
    cpu_set_t cpuset;
    char* locking;

    if (argc != 6) {
        usage(argv);
        exit(-1);
    };
    nthreads   = atoi(argv[1]);
    if (*argv[2] == 'c') {
        coarse = 1;
        locking = "coarse-grained";
    } else if (*argv[2] == 'f') {
        coarse = 0;
        locking = "fine-grained";
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
        if (coarse) {
            rc = pthread_create(&threads[i], NULL, worker_thread_coarse, (void *)NULL);
        } else {
            rc = pthread_create(&threads[i], NULL, worker_thread_fine, (void *)NULL);
        };
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
