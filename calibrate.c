#include <pthread.h>
#include <stdio.h>
#include <memcached_prof.h>

int niter;
pthread_mutex_t lock;

static void* worker_thread(void*arg) {
    int i;
    for (i = 0; i<niter; i++) {
        tracepoint(memcached, calib_lock);
        pthread_mutex_lock(&lock);
        pthread_mutex_unlock(&lock);
        tracepoint(memcached, calib_unlock);
    };
    return NULL;
}

int main(int argc, char* argv[]) {
    int i;
    int rc;
    pthread_t * threads;
    int nthreads;

    if (argc != 3) {
        fprintf(stderr, "usage: %s <num_threads> <num_iterations>\n", argv[0]);
        exit(-1);
    };
    nthreads = atoi(argv[1]);
    niter    = atoi(argv[2]);
    threads = (pthread_t*) malloc(nthreads*sizeof(pthread_t));
    pthread_mutex_init(&lock, NULL);

    tracepoint(memcached, start_calibrate);
    for (i = 0; i < nthreads; i++) {
        rc = pthread_create(&threads[i], NULL, worker_thread, (void *)NULL);
        if (rc){
            fprintf(stderr, "ERROR; return code from pthread_create() is %d\n", rc);
            exit(-1);
        };
    };
    for (i = 0; i < nthreads; i++) {
        pthread_join(threads[i], NULL);
    };
    tracepoint(memcached, end_calibrate);
    free(threads);
    return 0;
}


