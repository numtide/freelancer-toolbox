{
  pkgs ? import <nixpkgs> { },
  lib ? pkgs.lib,
}:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "harvest-rounder";
  version = "0.0.1";
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./pyproject.toml
      ./README.md
      ./harvest
      ./harvest_exporter
      ./harvest_rounder
      ./kimai
      ./kimai_exporter
      ./rest
    ];
  };

  pyproject = true;
  build-system = [ pkgs.python3.pkgs.hatchling ];

  doCheck = false;

  # Rich is a dependency of the shared pyproject.toml even though
  # harvest-rounder doesn't use it directly
  dependencies = [ pkgs.python3.pkgs.rich ];
}
