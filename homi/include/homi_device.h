enum homi_backend {
	HOMI_BACKEND_AISIO,
	HOMI_BACKEND_POSIX,
};

void
homi_device_set_backend(struct homi_opts *opts);
