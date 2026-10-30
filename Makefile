# SPDX-FileCopyrightText: Samsung Electronics Co., Ltd
#
# SPDX-License-Identifier: BSD-3-Clause

# Develop AiSIO on the xnvme-devenv guest, with an emulated AMD GPU and an
# NVMe controller behind one PCIe switch. 'make devenv' enters the host
# container CI runs the 'devenv' job in; the guest-* targets run inside it,
# and CI runs them too. Needs KVM.
#
#   make devenv
#   make guest-start guest-provision guest-test
#   make guest-stop

# The tag configs/devenv_guest.toml pins the guest by
DEVENV_IMAGE ?= ghcr.io/xnvme/xnvme-devenv/host:v0.15.0

# Guest images and disks, kept across 'make devenv' sessions
DEVENV_STATE ?= $(HOME)/.cache/aisio-devenv

# Rig names or files, layered in order as further configs; a name is one of
# the rigs the host container ships. The tasks expect compute-node-emulated's
# GPU and controller, so a further rig changes details of it
RIG ?= compute-node-emulated
RIGS_DIR ?= /opt/xnvme-devenv/rigs

OUTPUT ?= cijoe-output

rig_configs = $(foreach r,$(RIG),-c $(if $(filter %.toml,$(r)),$(r),$(RIGS_DIR)/$(r).toml))

.PHONY: devenv guest-start guest-provision guest-test guest-logs guest-stop

# Host networking puts the guest's SSH on the host's port 4200
devenv:
	mkdir -p $(DEVENV_STATE)/guests $(DEVENV_STATE)/system_imaging
	docker run --rm -it --privileged --network host \
		-v $(CURDIR):/aisio -w /aisio \
		-v $(DEVENV_STATE)/guests:/root/guests \
		-v $(DEVENV_STATE)/system_imaging:/root/system_imaging \
		$(DEVENV_IMAGE) bash

guest-start:
	cijoe --monitor \
		-c configs/devenv_guest.toml $(rig_configs) \
		-o $(OUTPUT)/devenv_start \
		tasks/devenv_start.yaml

# configs/devenv_guest.toml last, so its [os] is the guest's own
guest-provision:
	cijoe --monitor \
		-c configs/aisio.toml \
		-c configs/devenv_guest.toml \
		--facts $(OUTPUT)/devenv_start/facts.toml \
		-o $(OUTPUT)/setup_aisio \
		tasks/setup_aisio.yaml

# configs/devenv_guest.toml after configs/smoke.toml, so its controller is used.
# P2P first, as smoke_daemons.yaml formats the namespace and leaves daemons up
# when it fails
guest-test:
	cijoe --monitor \
		-c configs/smoke.toml \
		-c configs/devenv_guest.toml \
		-o $(OUTPUT)/smoke_p2p \
		tasks/smoke_p2p.yaml
	cijoe --monitor \
		-c configs/smoke.toml \
		-c configs/devenv_guest.toml \
		-o $(OUTPUT)/smoke_daemons \
		tasks/smoke_daemons.yaml

# A failed guest-test leaves the daemons running with their logs unread
guest-logs:
	cijoe \
		-c configs/smoke.toml \
		-c configs/devenv_guest.toml \
		-o $(OUTPUT)/smoke_daemons_logs \
		tasks/smoke_daemons.yaml logs

guest-stop:
	cijoe \
		-c configs/devenv_guest.toml $(rig_configs) \
		-o $(OUTPUT)/guest_stop \
		tasks/devenv_start.yaml guest_kill
