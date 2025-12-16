UDMABUF Import
==============

This directory contains a patch adding *dma-buf* importer functionality to *udmabuf* and two examples of using it to import a *dma-buf* and share its physical addresses with userspace.
One is using *udmabuf* to create a *dma-buf* from a *memfd*, the other is using the NVIDIA driver to create a *dma-buf* from memory allocated on the GPU.

Compile and Run
---------------

* ``make cpu`` builds the CPU example, ``./udmabuf_import_cpu`` runs it

* ``make gpu`` builds the GPU example, ``./udmabuf_import_gpu`` runs it

Prerequisites
-------------

A custom kernel is required for running these examples.
The instructions for installing the kernel can be found below.
This assumes Ubuntu 24.04, which comes with kernel 6.8.

Install Custom Kernel
^^^^^^^^^^^^^^^^^^^^^

* Get kernel source::

	  apt install linux-source

* Decompress source::

	  cd /usr/src/linux-source-*; tar -jxf linux-source-*.tar.bz2; cd linux-source-*

* Copy patches::

	  cp /root/git/aisio/udmabuf-import/patches/ .

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

