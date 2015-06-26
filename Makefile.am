bin_PROGRAMS = memcached_c memcached_f calibrate dummy
pkginclude_HEADERS = protocol_binary.h
noinst_PROGRAMS = dummy-debug calibrate-debug memcached_c-debug memcached_f-debug sizes testapp timedrun

BUILT_SOURCES=

testapp_SOURCES = testapp.c util.c util.h

timedrun_SOURCES = timedrun.c

memcached_c_SOURCES = memcached_prof.c \
		      memcached.c memcached.h \
                      hash.c hash.h \
                      slabs.c slabs.h \
                      items.c items.h \
                      assoc.c assoc.h \
                      thread.c daemon.c \
                      stats.c stats.h \
                      util.c util.h \
                      trace.h cache.h sasl_defs.h \
		      bench.c bench.h


calibrate_SOURCES = memcached_prof.c \
		    calibrate.c

dummy_SOURCES = memcached_prof.c \
	        dummy.c

memcached_prof.c: memcached_prof.tp
	lttng-gen-tp $<

if BUILD_CACHE
memcached_c_SOURCES += cache.c
testapp_SOURCES += cache.c
endif

if BUILD_SOLARIS_PRIVS
memcached_c_SOURCES += solaris_priv.c
endif

if ENABLE_SASL
memcached_c_SOURCES += sasl_defs.c
endif

memcached_c_debug_SOURCES = $(memcached_c_SOURCES)
memcached_c_CPPFLAGS = -DNDEBUG -DCOARSE
memcached_c_debug_LDADD = @PROFILER_LDFLAGS@ -llttng-ust -ldl
memcached_c_debug_CFLAGS = @PROFILER_FLAGS@

memcached_c_LDADD = -llttng-ust -ldl
memcached_c_DEPENDENCIES =
memcached_c_debug_DEPENDENCIES =

memcached_f_SOURCES = $(memcached_c_SOURCES)
memcached_f_debug_SOURCES = $(memcached_f_SOURCES)
memcached_f_CPPFLAGS = -DNDEBUG
memcached_f_debug_LDADD = @PROFILER_LDFLAGS@ -llttng-ust -ldl
memcached_f_debug_CFLAGS = @PROFILER_FLAGS@

memcached_f_LDADD = -llttng-ust -ldl
memcached_f_DEPENDENCIES =
memcached_f_debug_DEPENDENCIES =


calibrate_CPPFLAGS = -DNDEBUG

calibrate_LDADD = -llttng-ust -ldl
calibrate_DEPENDENCIES =

calibrate_debug_SOURCES = $(calibrate_SOURCES)
calibrate_debug_LDADD = @PROFILER_LDFLAGS@ -llttng-ust -ldl
calibrate_debug_CFLAGS = @PROFILER_FLAGS@
calibrate_debug_DEPENDENCIES =

dummy_CPPFLAGS = -DNDEBUG

dummy_LDADD = -llttng-ust -ldl
dummy_DEPENDENCIES =

dummy_debug_SOURCES = $(dummy_SOURCES)
dummy_debug_LDADD = @PROFILER_LDFLAGS@ -llttng-ust -ldl
dummy_debug_CFLAGS = @PROFILER_FLAGS@
dummy_debug_DEPENDENCIES =


CLEANFILES=

SUBDIRS = 
DIST_DIRS = scripts
EXTRA_DIST = scripts t memcached.spec memcached_dtrace.d version.m4

MOSTLYCLEANFILES = *.gcov *.gcno *.gcda *.tcov

test:	memcached_c-debug sizes testapp
	$(srcdir)/sizes
	$(srcdir)/testapp
	prove $(srcdir)/t
	@if test `basename $(PROFILER)` = "gcov"; then \
	  for file in memcached_c_debug-*.gc??; do \
	    mv -f $$file `echo $$file | sed 's/memcached_c_debug-//'`; \
	  done && \
	  for file in *.gcda; do \
	    srcfile=`echo $$file | sed 's/.gcda/.c/'`; \
	    if test -n "`echo $(memcached_c_debug_SOURCES) | grep $$srcfile`"; then \
	      echo `$(PROFILER) $$srcfile` | sed 's/'$$srcfile':.*//'; \
	    fi \
	  done \
	elif test `basename $(PROFILER)` = "tcov"; then \
	  files=`grep SRCFILE memcached_c-debug.profile/tcovd | sed 's/SRCFILE://' | sort | uniq` && \
	  $(PROFILER) -x memcached_c-debug.profile $$files 2>&1; \
	  for file in *.tcov; do \
	    srcfile=`echo $$file | sed 's/.tcov//'`; \
	    if test -n "`echo $(memcached_c_debug_SOURCES) | grep $$srcfile`"; then \
	      echo $$srcfile : `grep 'Percent of the file executed' $$file`; \
	    fi \
	  done \
	else :; fi

docs:
	(cat Doxyfile ; echo "PROJECT_NUMBER=`cat version.num`") | doxygen -

dist-hook:
	rm -f $(distdir)/*/*~ $(distdir)/t/lib/*~ $(distdir)/*~
