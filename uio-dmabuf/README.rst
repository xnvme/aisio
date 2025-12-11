UIO dma-buf
===========

This directory contains a patch adding *dma-buf* importer functionality to *UIO* and two examples of it to import a *dma-buf* and share its physical addresses with userspace.
One is using *udmabuf* to create a *dma-buf* from a *memfd*, the other is using the NVIDIA driver to create a *dma-buf* from memory allocated on the GPU.

Compile and Run
---------------

* ``make cpu`` builds the CPU example, ``./uio_dmabuf_cpu`` runs it

* ``make gpu`` builds the GPU example, ``./uio_dmabuf_gpu`` runs it

Prerequisites
-------------

A custom kernel is required for running these examples.
The instructions for installing the kernel can be found below.
This assumes Ubuntu 24.04, which comes with kernel 6.8.

Additionally, it requires a device bound to UIO.
For our example we use an NVMe drive bound to ``uio_pcie_generic``.

Install Custom Kernel
^^^^^^^^^^^^^^^^^^^^^

* Get kernel source::

	  apt install linux-source

* Decompress source::

	  cd /usr/src/linux-source-*; tar -jxf linux-source-*.tar.bz2; cd linux-source-*

* Copy patches::

	  cp /root/git/aisio/uio-dmabuf/patches/ .

* Apply patches (add `-R` to reverse)::

	  git apply --reject *.patch

* Get config:: 

	  cp /boot/config-$(uname -r) .config

* Configure::

	  scripts/config --disable DEBUG_INFO; scripts/config --set-str SYSTEM_TRUSTED_KEYS ""; scripts/config --set-str SYSTEM_REVOCATION_KEYS ""; scripts/config --disable MODULE_SIG

* Prepare::

	  make oldconfig scripts prepare modules_prepare

* Build::

	  make -j $(nproc) bindeb-pkg LOCALVERSION=-dmabuf

* Install::

	  dpkg -i ../*.deb

Bind NVMe to UIO
^^^^^^^^^^^^^^^^

* Load UIO driver::

	  modprobe uio_pci_generic

* Unbind from NVMe driver::

	  echo "0000:01:00.0" > /sys/bus/pci/devices/0000\:01\:00.0/driver/unbind

* Add UIO to driver overide::

	  echo uio_pci_generic > /sys/bus/pci/devices/0000\:01\:00.0/driver_override

* Bind to UIO::

	  echo "0000:01:00.0" > /sys/bus/pci/drivers/uio_pci_generic/bind

