define default-help
# Build and start
endef
.PHONY: default
default: build start

define build-help
# Compile and configure HOMI service
endef
.PHONY: build
build:
	gcc daemon.c -o daemon.o
	cp ./homi.service /etc/systemd/system
	@echo "## Replace assumed location of executable"
	sed -i "s|/root/git/aisio/homi|$(CURDIR)|" /etc/systemd/system/homi.service
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
