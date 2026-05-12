#ifndef HOMID_H
#define HOMID_H

struct homid {
  struct homid_ipc_connection *conn;
  struct homid_device *dev;	///< Pointer to array of 'struct homid_device'
  unsigned int ndevs;		///< Number of devices
};

#endif /* HOMID_H */
