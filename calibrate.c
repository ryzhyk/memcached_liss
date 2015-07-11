#define _GNU_SOURCE

#include <pthread.h>
#include <stdio.h>
#include <memcached_prof.h>

int niter;
int nidle;
pthread_mutex_t lock;

static void* Worker_thread_async(void*arg) {
    int i;
    volatile int j;
    tracepoint(memcached, start_calibrate_thread);
    for (i = 0; i<niter; i++) {
        for (j=0; j<nidle; j++);
        for (j=0; j<nidle; j++);
    };
    tracepoint(memcached, end_calibrate_thread);
    pthread_exit(NULL);
}

static void* Worker_thread1(void*arg) {
    int i;
    volatile int j;
    tracepoint(memcached, start_calibrate_thread);
    for (i = 0; i<niter; i++) {
        pthread_mutex_lock(&lock);
        for (j=0; j<nidle; j++);
        pthread_mutex_unlock(&lock);
        for (j=0; j<nidle; j++);
    };
    tracepoint(memcached, end_calibrate_thread);
    pthread_exit(NULL);
}


static void* worker_thread_async(void*arg) {
    int i;
    volatile int j;
    tracepoint(memcached, start_calibrate_thread);
    for (i = 0; i<niter; i++) {
        for (j=0; j<nidle; j++);
    };
    tracepoint(memcached, end_calibrate_thread);
    pthread_exit(NULL);
}

static void* worker_thread1(void*arg) {
    int i;
    volatile int j;
    tracepoint(memcached, start_calibrate_thread);
    for (i = 0; i<niter; i++) {
        pthread_mutex_lock(&lock);
        for (j=0; j<nidle; j++);
        pthread_mutex_unlock(&lock);
    };
    tracepoint(memcached, end_calibrate_thread);
    pthread_exit(NULL);
}



int main(int argc, char* argv[]) {
    int i;
    int rc;
    pthread_t * threads;
    int nthreads;
    cpu_set_t cpuset;
    void* (*tfunc)(void*);

    if (argc != 6) {
        fprintf(stderr, "usage: %s s|a l|L <num_threads> <num_iterations> <num_idle>\n", argv[0]);
        exit(-1);
    };

    if (argv[1][0] == 's')
        if (argv[2][0] == 'l')
            tfunc = worker_thread1;
        else
            tfunc = Worker_thread1;
    else
        if (argv[2][0] == 'l')
            tfunc = worker_thread_async;
        else
            tfunc = Worker_thread_async;


    nthreads = atoi(argv[3]);
    niter    = atoi(argv[4]);
    nidle    = atoi(argv[5]);
    printf("Lock calibration (%s) run with %i threads, %i iterations, %i idle cycles\n", argv[1], nthreads, niter, nidle);

    threads = (pthread_t*) calloc(nthreads, sizeof(pthread_t));
    pthread_mutex_init(&lock, NULL);

    tracepoint(memcached, start_calibrate);
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
    tracepoint(memcached, end_calibrate);
    free(threads);
    return 0;
}


