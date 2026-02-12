project('tomlc17', 'c')

toml_lib = static_library('toml',
  'src/tomlc17.c',
  include_directories: include_directories('src'),
)

toml_dep = declare_dependency(
  include_directories: include_directories('src'),
  link_with: toml_lib,
)
