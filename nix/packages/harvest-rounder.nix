{ pkgs }:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "harvest-rounder";
  version = "0.1.0";
  src = ../../packages/harvest;

  pyproject = true;
  build-system = [ pkgs.python3.pkgs.hatchling ];

  doCheck = false;

  # Rich is a dependency of the shared pyproject.toml even though
  # harvest-rounder doesn't use it directly
  dependencies = [ pkgs.python3.pkgs.rich ];
}
