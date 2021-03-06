SHELL = /bin/bash
export PREFIX ?= $(abspath env)

ifeq ($(OS),Windows_NT)
	PLATFORM := Windows
else
	PLATFORM := $(shell uname -s)
endif

ifeq ($(PLATFORM),Darwin)
	CCACHE_PATH = /usr/local/opt/ccache/bin
	LIBSUFFIX = dylib
	PY3 ?= $(realpath /Library/Frameworks/Python.framework/Versions/3.7/bin/python3.7)
	WHEELTOOL = delocate
	SQLITE_VERSION := $(shell /usr/local/opt/sqlite3/bin/sqlite3 --version 2>/dev/null | awk '{print $$1}')
else ifeq ($(PLATFORM),Linux)
	LIBSUFFIX = so
	CCACHE_PATH = /usr/lib/ccache
	CCACHE_PATH := $(or $(CCACHE_PATH),/usr/lib64/ccache)
	WHEELTOOL = auditwheel
	include ../sqlite/version.mk  # SQLITE_VERSION
endif
PY3 := $(or $(PY3),python3.7)

# use ccache if available
export PATH := $(CCACHE_PATH):$(PREFIX)/bin:$(PATH)

ifeq ($(SQLITE_VERSION),3.32.1)
	# fix :-(
	APSW_VERSION := 3.32.2-r1
endif
APSW_VERSION ?= $(SQLITE_VERSION)-r1
APSW_ARCHIVE := apsw-$(APSW_VERSION).tar.gz
APSW_BUILD_OPTS := --enable-all-extensions --enable=load_extension
sqlite_src := src/sqlite3/config.status

# default target
.PHONY: all
all: wheel

.PHONY: clean
clean:
	-$(RM) -r env
	-$(RM) -r wheel wheelhouse
	-$(RM) -r src/build src/dist src/.eggs

.PHONY: cleaner
cleaner: clean
	-(cd src && python3 setup.py clean)

.PHONY: cleanest
cleanest: clean
	-$(RM) -r src

.PHONY: clean-configure
clean-configure:

#
# Download Archives
#

$(APSW_ARCHIVE):
	@echo "APSW_VERSION=$(APSW_VERSION) SQLITE_VERSION=$(SQLITE_VERSION) APSW_ARCHIVE=$(APSW_ARCHIVE)"
	wget "https://github.com/rogerbinns/apsw/archive/$(APSW_VERSION).tar.gz" -O $@

.PHONY: archive
archive: $(APSW_ARCHIVE)

#
# Extract Archives
#

src: $(APSW_ARCHIVE)
	rm -rf $@
	mkdir -p $@
	@echo "Extracting $(APSW_ARCHIVE) ..."
	tar xzf $(APSW_ARCHIVE) --strip-components=1 -C $@

$(sqlite_src): export SSL_CERT_FILE ?= $(CERTIFI_SSL_CERT_FILE)
$(sqlite_src): | src
	# fetch sqlite amalgamation
	cd src && python setup.py fetch \
		--sqlite --version=$(SQLITE_VERSION) \
		--missing-checksum-ok

.PHONY: source
source: $(sqlite_src)

#
# APSW
#

.PHONY: py-fix-Darwin
py-fix-Darwin:
# 	for SO in src/build/lib.macosx*/apsw.*.so; do \
# 		echo $$SO; \
# 		install_name_tool \
# 			-change "/usr/local/opt/sqlite/lib/libsqlite3.0.dylib" "@rpath/libsqlite3.0.dylib" \
# 			"$$SO"; \
# 	done

.PHONY: py-fix-Linux
py-fix-Linux:

.PHONY: install
install: $(sqlite_src)
	@echo 'CFLAGS=$(CFLAGS) LDFLAGS=$(LDFLAGS) PY3=$(PY3)'
	cd src && python setup.py install $(APSW_BUILD_OPTS)

.PHONY: wheel
wheel: $(sqlite_src)
	@echo 'CFLAGS=$(CFLAGS) LDFLAGS=$(LDFLAGS) PY3=$(PY3)'
	cd src && python setup.py --no-user-cfg \
		build $(APSW_BUILD_OPTS)

	$(MAKE) py-fix-$(PLATFORM)

	cd src && python setup.py  --no-user-cfg \
		bdist_wheel -d $(abspath $@)

	$(MAKE) py-deps-$(PLATFORM)

.PHONY: py-deps-Darwin
py-deps-Darwin:
	delocate-listdeps wheel/*.whl

.PHONY: py-deps-Linux
py-deps-Linux:
	auditwheel show wheel/*.whl
