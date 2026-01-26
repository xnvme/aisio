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

Limitations and errors
----------------------

This section describes the limitations discovered while using the dma-buf interface and the errors associated with these.

File descriptor limits
^^^^^^^^^^^^^^^^^^^^^^

*dma-buf* is based on file descriptors and every new dma-buf FD will count as opening a file.
Thus, you can easily run into errno 24 "EMFILE 24 Too many open files". To avoid this, you can increase your user limits.
You can temporarily increase them with::

	ulimit -n 1000000

To permanently increase it, add the following lines to `/etc/security/limits.conf`::

	<username> - nofile 100000

You can use '*' to set the limit for all users. However, this will not apply to the root user.
n this case you need to add a separat line where <username> is root.

The value chosen above is arbitrary, if you are interested to see the system wide limit run::

	cat /proc/sys/fs/file-max

GPU memory limitations
^^^^^^^^^^^^^^^^^^^^^^

NVIDIA GPUs have two memory regions that we care about. One is called the FB (frame buffer) memory, this memory is what we typically consider device/GPU memory.
We use this memory when making memory allocations on the GPU by running `cudaMalloc`, `cuMemAlloc` or similar.
The second region is the BAR1 memory. This is used to map the FB Memory allowing it to be directly accessed by the CPU or through P2P DMA Transfers.
Note, both regions might have a portion of memory reserved for the GPU driver.

The sizes of the memory reqions can be found by running the following::

	nvidia-smi -q -d memory

The output of this command should look something like this::

	...
	FB Memory Usage
        Total                             : 6138 MiB
        Reserved                          : 330 MiB
        Used                              : 0 MiB
        Free                              : 5809 MiB
    BAR1 Memory Usage
        Total                             : 8192 MiB
        Used                              : 1 MiB
        Free                              : 8191 MiB
	...

If we run out of memory from either region the execution will fail.
FB memory runs out if we make too large or too many allocations.
The BAR1 memory runs out if we make too large or too many mappings. This means that we might have many allocations with a total size below the FB limit,
but the size of the mappings exceeds the available BAR1 memory.
This is true both when using the NVIDIA kernel P2P API or the NVIDIA Driver API to create the mappings.

The size of the mapping scales with the size of the allocation. On one system we saw an 140KiB allocation take up 2MiB of BAR1 memory,
while an 8MiB allocation took up 8MiB of BAR1.
We saw that it is possible to run out of BAR1 memory before FB memory by creating a large amount of small (e.g., 140KiB) allocations and mapping them.
This made the program crash and `dmesg` showed the following errors::

	NVRM: dmaAllocMapping_GM107: can't alloc VA space for mapping.
	NVRM: nvAssertOkFailedNoLog: Assertion failed: Out of memory [NV_ERR_NO_MEMORY] (0x00000051)

A different problem arises with single large allocations.
On one GPU (NVIDIA RTX A2000) we found a threshold of 1048560 * 4KiB, if more than this is allocated, the IO CUDA Kernels runs forever.
However, with multiple allocations we can exceed this amount without problems. It is unclear why.
We have not been able to reproduce this with other GPUs.
