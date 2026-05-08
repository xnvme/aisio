define default-help
# Build and start
endef
.PHONY: default
default: clean config build install

define clean-help
# Remove builddir
endef
.PHONY: clean
clean:
	@rm -r builddir || echo "Nothing to clean, continuing"

define config-help
# configure HOMI service
endef
.PHONY: config
config:
	meson setup builddir

define build-help
# Compile HOMI service
endef
.PHONY: build
build:
	meson compile -C builddir

define install-help
# install HOMI service
endef
.PHONY: install
install:
	meson install -C builddir
	ldconfig
	systemctl daemon-reload

define start-help
# Run systemctl start homi
endef
.PHONY: start
start:
	systemctl start homi
	@echo "## Started HOMI service"

define stop-help
# Run systemctl stop homi
endef
.PHONY: stop
stop:
	systemctl stop homi
	@echo "## Stopped HOMI service"

define log-help
# See the 10 last log entries for the HOMI service
endef
.PHONY: log
log:
	journalctl -u homi -n10

define status-help
# Run systemctl status homi
endef
.PHONY: status
status:
	systemctl status homi || :
