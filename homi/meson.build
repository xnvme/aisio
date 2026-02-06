project('homi', 'c',
  version: '0.1.0',
  meson_version: '>=0.55.0',
  default_options: [
    'c_std=gnu11',
    'warning_level=2',
    'buildtype=release',
  ],
)

homi_dependencies = []

sources = files(
  'src/daemon.c',
  'src/homi_log.c',
)

include_dirs = include_directories('include')

bindir = join_paths(get_option('prefix'), get_option('bindir'))

executable('homi',
  sources: sources,
  dependencies: homi_dependencies,
  include_directories: include_dirs,
  install: true,
  install_dir: bindir,
)

configure_file(
  input: 'homi.service.in',
  output: 'homi.service',
  install: true,
  install_dir: join_paths(get_option('libdir'), 'systemd', 'system'),
  configuration: {
    'bindir': bindir,
  },
)
