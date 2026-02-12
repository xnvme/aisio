project('homi', 'c',
  version: '0.1.0',
  meson_version: '>=0.58.0',
  default_options: [
    'c_std=gnu11',
    'warning_level=2',
    'buildtype=release',
  ],
)

systemd = dependency('systemd')

homi_dependencies = []

sources = files(
  'src/homi.c',
  'src/homi_log.c',
)

include_dirs = include_directories('include')

bindir = join_paths(get_option('prefix'), get_option('bindir'))

executable('homid',
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
  install_dir: systemd.get_variable('systemdsystemunitdir'),
  configuration: {
    'bindir': bindir,
  },
)
