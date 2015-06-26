#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <stdatomic.h>
#include <unistd.h>

#include <memcached_prof.h>
#include <memcached.h>
/*#include "items.h"*/
/*#include "thread.h"*/

#define NKEYS 1000
#define ITEM_SIZE 1000

/*#define COARSE*/

#ifdef COARSE

#define lock_coarse(op)   {\
    lock(op);\
    tracepoint(memcached, c_begin); \
    atomic_store(&inside_c, 1); \
    atomic_store(&num_sections, 0); \
}
#define unlock_coarse(op) { \
    atomic_store(&inside_c, 0); \
    tracepoint(memcached, c_end, atomic_load(&num_sections)); \
    unlock(op); \
}

#define lock_fine(op)     { \
    atomic_store(&inside_cc, 1); \
    atomic_fetch_add(&num_sections, 1); \
}
#define unlock_fine(op)   { \
    atomic_store(&inside_cc, 0); \
}

#else

#define lock_coarse(op)   { \
    tracepoint(memcached, c_begin); \
    atomic_store(&inside_c, 1); \
    atomic_store(&num_sections, 0); \
}
#define unlock_coarse(op) { \
    atomic_store(&inside_c, 0); \
    tracepoint(memcached, c_end, atomic_load(&num_sections)); \
}

#define lock_fine(op)     {\
    lock(op); \
    atomic_store(&inside_cc, 1); \
    atomic_fetch_add(&num_sections, 1); \
}
#define unlock_fine(op)   { \
    atomic_store(&inside_cc, 0); \
    unlock(op); \
}

#endif

typedef enum {ACTION_STORE, ACTION_GET, ACTION_DELETE} op_t;

atomic_ushort contention_counter = 0;

atomic_ushort inside_c = 0;
atomic_ushort inside_cc = 0;
atomic_ushort num_sections = 0;

static enum store_item_type do_store(item *it, int comm);
static void op_store();
static void op_get();
static void op_delete();

static void lock(char* op) {
    atomic_fetch_add(&contention_counter, 1);
    pthread_mutex_lock(&cache_lock);
}

static void unlock(char * op) {
    pthread_mutex_unlock(&cache_lock);
    atomic_fetch_sub(&contention_counter, 1);
}


void *monitor_thread(void *arg) {
    while (1) {
        if (atomic_load(&inside_c))
            tracepoint(memcached, inside_cc, atomic_load(&inside_cc));
        usleep(100);
    };
}

void random_op () {
    op_t op;
    long int r = random();
    if (r < RAND_MAX * 0.4) {        /* 40% */
        op = ACTION_STORE;
    } else if (r < RAND_MAX * 0.9) { /* 50% */
        op = ACTION_GET;
    } else {                         /* 10% */
        op = ACTION_DELETE;
    };

    lock_coarse("op_store");
    switch (op) {
        case ACTION_STORE:  op_store();
        case ACTION_GET:    op_get();
        case ACTION_DELETE: op_delete();
    };  
    unlock_coarse("op_store");
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

    lock_fine("op_store");
    tracepoint(memcached, contention, atomic_load(&contention_counter));
    it = do_item_alloc(key, strlen(key), 0, realtime(time(NULL) + 1000), ITEM_SIZE);
    unlock_fine("op_store");

    if (it != NULL) {
        do_store (it, comm);
        lock_fine("op_store");
        do_item_remove (it);
        unlock_fine("op_store");
    };

/*    printf("%li: op_store done\n", pthread_self());*/
}

static void op_get() {
    char key[24];
    item *it;

/*    printf("%li: op_get\n", pthread_self());*/
    lock_fine("op_get");
    sprintf(key, "%li", random() % NKEYS);
    it = do_item_get (key, strlen (key));
    if (it) {
        do_item_remove (it);
    };
    unlock_fine("op_get");
/*    printf("%li: op_get done\n", pthread_self());*/
}

static void op_delete() {
    char key[24];
    item *it;

/*    printf("%li: op_delete\n", pthread_self());*/
    lock_fine("op_delete");
/*    sprintf(key, "%li", random() % NKEYS);*/
    it = do_item_get(key, strlen(key));
    if (it) {
        do_item_unlink(it);
        do_item_remove(it);      /* release our reference */
    };
    unlock_fine("op_delete");

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

    lock_fine("do_store");
    old_it = do_item_get(key, it->nkey);
    unlock_fine("do_store");
    
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

            lock_fine("do_store");
            new_it = do_item_alloc(key, it->nkey, flags, old_it->exptime, it->nbytes + old_it->nbytes - 2 /* CRLF */);
            unlock_fine("do_store");

            if (new_it == NULL) {
                /* SERVER_ERROR out of memory */
                if (old_it != NULL) {
                    lock_fine("do_store");
                    do_item_remove(old_it);
                    unlock_fine("do_store");
                };

                return NOT_STORED;
            }

            /* copy data from it and old_it to new_it */

            if (comm == NREAD_APPEND) {
                memcpy(ITEM_data(new_it), ITEM_data(old_it), old_it->nbytes);
                memcpy(ITEM_data(new_it) + old_it->nbytes - 2 /* CRLF */, ITEM_data(it), it->nbytes);
            } else {
                /* NREAD_PREPEND */
                memcpy(ITEM_data(new_it), ITEM_data(it), it->nbytes);
                memcpy(ITEM_data(new_it) + it->nbytes - 2 /* CRLF */, ITEM_data(old_it), old_it->nbytes);
            }

            it = new_it;
        }
    }

    lock_fine("do_store");
    if (stored == NOT_STORED) {
        if (old_it != NULL)
            do_item_replace(old_it, it);
        else
            do_item_link(it);

        stored = STORED;
    }
    unlock_fine("do_store");

    if (old_it != NULL) {
        lock_fine("do_store");
        do_item_remove(old_it);         /* release our reference */
        unlock_fine("do_store");
    }
    if (new_it != NULL) {
        lock_fine("do_store");
        do_item_remove(new_it);
        unlock_fine("do_store");
    }

    return stored;
}
