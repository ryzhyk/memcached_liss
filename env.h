#define random() ((unsigned long) nondet)

#define RAND_MAX 32767

typedef unsigned long size_t;
typedef unsigned long time_t;

int sprintf(char *str, const char *format, ...);
size_t strlen(const char *s);
long int strtol(const char *nptr, char **endptr, int base);
time_t time(time_t *t);

#define memcpy(dst, src, n) {*(unsigned char*)(dst) = *(unsigned char*)((src) + n);}

#define NULL 0

#define ITEM_LINKED 1
#define ITEM_CAS 2

#define NREAD_ADD 1
#define NREAD_SET 2
#define NREAD_REPLACE 3
#define NREAD_APPEND 4
#define NREAD_PREPEND 5
#define NREAD_CAS 6

enum store_item_type {
    NOT_STORED=0, STORED, EXISTS, NOT_FOUND
};

#define tracepoint(s,n,...) {}

typedef unsigned int rel_time_t;

rel_time_t realtime(const time_t exptime);

typedef struct {
    unsigned char nkey;       /* key length, w/terminating null and padding */
    rel_time_t    exptime;    /* expire time */
    int           nbytes;     /* size of data */
    unsigned char it_flags;   /* ITEM_* above */
    unsigned char nsuffix;    /* length of flags-and-length string */
    void          * end[];
} item;

#define ITEM_key(item) (((char*)&((item)->end[0])) \
         + (((item)->it_flags & ITEM_CAS) ? sizeof(unsigned long long) : 0))

#define ITEM_suffix(item) ((char*) &((item)->end[0]) + (item)->nkey + 1 \
         + (((item)->it_flags & ITEM_CAS) ? sizeof(unsigned long long) : 0))

#define ITEM_data(item) ((char*) &((item)->end[0]) + (item)->nkey + 1 \
         + (item)->nsuffix \
         + (((item)->it_flags & ITEM_CAS) ? sizeof(unsigned long long) : 0))

int hash;

item *do_item_alloc(char *key, const size_t nkey, const int flags, const rel_time_t exptime, const int nbytes) {
    hash = nondet;
    return (item *)(unsigned long)nondet;
}

#define do_item_remove(it) { \
    it = (item*) (unsigned long) nondet; \
    hash = nondet; \
}

#define do_item_unlink(it) { \
    it = (item*) (unsigned long) nondet; \
    hash = nondet; \
}

item *do_item_get(const char *key, const size_t nkey) {
    return (item*) (unsigned long)(nondet + hash);
} 

int do_item_replace(item *it, item *new_it) {
    hash = nondet;
    return nondet;
}

int do_item_link(item *it) {
    hash = nondet;
    return nondet;
}
