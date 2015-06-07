#define _GNU_SOURCE

#include <pthread.h>
#include <stdio.h>
#include <memcached_prof.h>

void* worker_thread(void*arg);

int niter;
pthread_mutex_t lock;

void* worker_thread(void*arg) {
    int i;
    tracepoint(memcached, start_calibrate_thread);
    for (i = 0; i<niter; i++) {
        //tracepoint(memcached, calib_lock);
        pthread_mutex_lock(&lock);
        
        pthread_mutex_unlock(&lock);
        //tracepoint(memcached, calib_unlock);
    };
    tracepoint(memcached, end_calibrate_thread);
    pthread_exit(NULL);
}

int main(int argc, char* argv[]) {
    int i;
    int rc;
    pthread_t * threads;
    int nthreads;
/*    cpu_set_t cpuset;*/

    if (argc != 3) {
        fprintf(stderr, "usage: %s <num_threads> <num_iterations>\n", argv[0]);
        exit(-1);
    };
    nthreads = atoi(argv[1]);
    niter    = atoi(argv[2]);
    printf("Lock calibration run with %i threads and %i iterations\n", nthreads, niter);

    threads = (pthread_t*) calloc(nthreads, sizeof(pthread_t));
    pthread_mutex_init(&lock, NULL);

    tracepoint(memcached, start_calibrate);
    for (i = 0; i < nthreads; i++) {
        rc = pthread_create(&threads[i], NULL, worker_thread, (void *)NULL);
        if (rc){
            fprintf(stderr, "ERROR; return code from pthread_create() is %d\n", rc);
            exit(-1);
        };
/*        CPU_ZERO(&cpuset);*/
/*        CPU_SET(i, &cpuset); */
/*        rc = pthread_setaffinity_np(threads[i], sizeof(cpu_set_t), &cpuset);*/
/*        if (rc){*/
/*            fprintf(stderr, "ERROR; return code from pthread_setaffinity_np(%i) is %d\n", i, rc);*/
/*            exit(-1);*/
/*        };*/
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


