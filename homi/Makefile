define default-help
# Build and start
endef
.PHONY: default
default: clean build install start

define clean-help
# Remove builddir
endef
.PHONY: clean
clean:
	@rm -r builddir || echo "Nothing to clean, continuing"

define build-help
# Compile and configure HOMI service
endef
.PHONY: build
build:
	meson setup builddir
	meson compile -C builddir

define install-help
# Compile and configure HOMI service
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
