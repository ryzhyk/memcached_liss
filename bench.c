#ifdef LISS

#include <langinc.h>
#include "env.h"

#else

#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <stdatomic.h>
#include <unistd.h>

#include <memcached_prof.h>
#include <memcached.h>

#define yield() {}

#endif

#define NKEYS 1000
//#define ITEM_SIZE 10000

/*#define COARSE*/

#ifndef LISS
atomic_ushort contention_counter = 0;

atomic_ushort inside_c = 0;
atomic_ushort inside_cc = 0;
atomic_ushort num_sections = 0;
atomic_short block_id = 0;

#define MAX_BLOCK_ID 8

unsigned short block_cnts[MAX_BLOCK_ID+1];

#define RESET_BLOCK_COUNTS { \
    int _i;\
    for (_i = 0; _i <= MAX_BLOCK_ID; _i++) { \
        block_cnts[_i] = 0; \
    }; \
}

#define SET_BLOCK_ID(_id) { \
    block_cnts[_id]++; \
    atomic_store(&block_id, _id); \
}

#define READ_DUMMY {}

#endif

#ifdef LISS

#define lock_coarse()   {}
#define unlock_coarse() {}
#define lock_fine()     {}
#define unlock_fine()   {}

int global_dummy;

#define RESET_BLOCK_COUNTS {}
#define SET_BLOCK_ID(_id) {}
#define READ_DUMMY {int local_dummy = global_dummy;}

#else 

#ifdef COARSE

#define lock_coarse()   {\
    lock();\
    tracepoint(memcached, c_begin); \
    atomic_store(&inside_c, 1); \
    atomic_store(&num_sections, 0); \
}
#define unlock_coarse() { \
    atomic_store(&inside_c, 0); \
    tracepoint(memcached, c_end, atomic_load(&num_sections)); \
    unlock(); \
}

#define lock_fine()     { \
    atomic_store(&inside_cc, 1); \
    atomic_fetch_add(&num_sections, 1); \
}
#define unlock_fine()   { \
    atomic_store(&inside_cc, 0); \
}

#else

#define lock_coarse()   { \
    lock(); tracepoint(memcached, c_begin); \
    atomic_store(&inside_c, 1); \
    atomic_store(&num_sections, 0); \
}
#define unlock_coarse() { \
    atomic_store(&inside_c, 0); \
    tracepoint(memcached, c_end, atomic_load(&num_sections)); unlock(); \
}

#define lock_fine()     {\
    lock(); \
    atomic_store(&inside_cc, 1); \
    atomic_fetch_add(&num_sections, 1); \
}
#define unlock_fine()   { \
    atomic_store(&inside_cc, 0); \
    unlock(); \
}

#endif

static void lock() {
    atomic_fetch_add(&contention_counter, 1);
    pthread_mutex_lock(&cache_lock);
}

static void unlock() {
    pthread_mutex_unlock(&cache_lock);
    atomic_fetch_sub(&contention_counter, 1);
}

#endif

typedef enum {ACTION_STORE, ACTION_GET, ACTION_DELETE} op_t;

static enum store_item_type do_store(item *it, int comm);
static void op_store();
static void op_get();
static void op_delete();

#ifndef LISS
void *monitor_thread(void *arg) {
    while (1) {
        if (atomic_load(&inside_c))
            tracepoint(memcached, inside_cc, atomic_load(&inside_cc));

        tracepoint(memcached, block_id, atomic_load(&block_id));
        usleep(100);
    };
}
#endif

void random_op () {
    op_t op;

    RESET_BLOCK_COUNTS;
    SET_BLOCK_ID(0);
    long int r = random();
    if (r < RAND_MAX * 0.4) {        /* 40% */
        op = ACTION_STORE;
    } else if (r < RAND_MAX * 0.9) { /* 50% */
        op = ACTION_GET;
    } else {                         /* 10% */
        op = ACTION_DELETE;
    };


    lock_coarse();
    SET_BLOCK_ID(1);
    op_store();
    op_get();
//    switch (op) {
//        case ACTION_GET:    op_get();
//        case ACTION_STORE:  op_store();
////        case ACTION_DELETE: op_delete();
//    };
    unlock_coarse();
    SET_BLOCK_ID(4);
    tracepoint(memcached, blk_cnts, block_cnts, MAX_BLOCK_ID + 1);
}

static void op_store() {
    item *it;
    unsigned long r;
    int comm;
    char key[24];

/*    printf("%li: op_store\n", pthread_self());*/
    r = random () % 3;
    if (r == 0) {
        comm = NREAD_SET;
    } else if (r == 1) {
        comm = NREAD_APPEND;
    } else {
        comm = NREAD_PREPEND;
    };

    sprintf(key, "%li", random() % NKEYS);

    tracepoint(memcached, contention, atomic_load(&contention_counter));
    it = do_item_alloc(key, strlen(key), 0, realtime(time(NULL) + 1000), settings.item_size);

    if (it != NULL) {
        do_store (it, comm);
        do_item_remove (it);
    };

/*    printf("%li: op_store done\n", pthread_self());*/
}

static void op_get() {
    char key[24];
    item *it;

/*    printf("%li: op_get\n", pthread_self());*/
    sprintf(key, "%li", random() % NKEYS);
//    SET_BLOCK_ID(7);
    it = do_item_get (key, strlen (key));
    if (it) {
        do_item_remove (it);
    };
//    SET_BLOCK_ID(8);
/*    printf("%li: op_get done\n", pthread_self());*/
}

static void op_delete() {
    char key[24];
    item *it;

    SET_BLOCK_ID(5);
/*    printf("%li: op_delete\n", pthread_self());*/
/*    sprintf(key, "%li", random() % NKEYS);*/
    it = do_item_get(key, strlen(key));
    if (it) {
        do_item_unlink(it);
        do_item_remove(it);      /* release our reference */
    };
    SET_BLOCK_ID(6);

/*    printf("%li: op_delete done\n", pthread_self());*/
}

/*
 * Stores an item in the cache according to the semantics of one of the set
 * commands. In threaded mode, this is protected by the cache lock.
 *
 * Returns the state of storage.
 */
static enum store_item_type do_store(item *it, int comm) {
    char *key = ITEM_key(it);
    item *old_it;
    enum store_item_type stored = NOT_STORED;

    item *new_it = NULL;
    int flags;

    old_it = do_item_get(key, it->nkey);
    
    /*
     * Append - combine new and old record into single one. Here it's
     * atomic and thread-safe.
     */
    if ((comm == NREAD_APPEND || comm == NREAD_PREPEND) && (old_it != NULL)) {
        /*
         * Validate CAS
         */
/*        if (ITEM_get_cas(it) != 0) {*/
/*            // CAS much be equal*/
/*            if (ITEM_get_cas(it) != ITEM_get_cas(old_it)) {*/
/*                stored = EXISTS;*/
/*            }*/
/*        }*/

        if (stored == NOT_STORED) {
            /* we have it and old_it here - alloc memory to hold both */
            /* flags was already lost - so recover them from ITEM_suffix(it) */

            flags = (int) strtol(ITEM_suffix(old_it), (char **) NULL, 10);

            new_it = do_item_alloc(key, it->nkey, flags, old_it->exptime, it->nbytes + old_it->nbytes - 2 /* CRLF */);

            if (new_it == NULL) {
                /* SERVER_ERROR out of memory */
                if (old_it != NULL) {
                    do_item_remove(old_it);
                };
                SET_BLOCK_ID(3);
                return NOT_STORED;
            }

            yield(); unlock_fine();
            SET_BLOCK_ID(2);
            /* copy data from it and old_it to new_it */

            if (comm == NREAD_APPEND) {
                memcpy(ITEM_data(new_it), ITEM_data(old_it), old_it->nbytes);
                memcpy(ITEM_data(new_it) + old_it->nbytes - 2 /* CRLF */, ITEM_data(it), it->nbytes);
            } else {
                /* NREAD_PREPEND */
                memcpy(ITEM_data(new_it), ITEM_data(it), it->nbytes);
                memcpy(ITEM_data(new_it) + it->nbytes - 2 /* CRLF */, ITEM_data(old_it), old_it->nbytes);
            }

            READ_DUMMY; lock_fine();
            it = new_it;
        }
    }
    SET_BLOCK_ID(3);

    if (stored == NOT_STORED) {
        if (old_it != NULL)
            do_item_replace(old_it, it);
        else
            do_item_link(it);

        stored = STORED;
    }

    if (old_it != NULL) {
        do_item_remove(old_it);         /* release our reference */
    }
    if (new_it != NULL) {
        do_item_remove(new_it);
    }

    return stored;
}

#ifdef LISS

void tfunc () {
    while (nondet) {
        random_op();
        yield();
    };
}

void thread_1() {
    tfunc();
}

void thread_2() {
    tfunc();
}

#endif
