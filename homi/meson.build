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

toml = subproject('tomlc17')
toml_dep = toml.get_variable('toml_dep')

xal_dep = dependency('xal', method: 'pkg-config', required: true)

xnvme_dep = dependency('xnvme', method: 'pkg-config', required: true)

homi_dependencies = [
	toml_dep,
	xal_dep,
	xnvme_dep
]

sources = files(
  'src/homid.c',
  'src/homid_ipc.c',
  'src/homid_log.c',
  'src/homid_xal.c',
  'src/homid_opts.c',
  'src/homi_proto.c',
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

library('homic',
  sources: ['src/homic.c', 'src/homi_proto.c'],
  dependencies: [xal_dep],
  include_directories: include_dirs,
  install: true,
)

install_headers('include/homic.h')

config_dir = join_paths('/etc', 'homi')
config_name = 'homi.conf'

configure_file(
  input: 'homi.service.in',
  output: 'homi.service',
  install: true,
  install_dir: systemd.get_variable('systemdsystemunitdir'),
  configuration: {
    'bindir': bindir,
    'config': join_paths(config_dir, config_name),
  },
)

message('Please edit the configuration file at /etc/homi/homi.conf')
configure_file(
  input: 'config/homi.conf.in',
  output: config_name,
  install: true,
  install_dir: config_dir,
  copy: true,
)
