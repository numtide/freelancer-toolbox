{ pkgs, perSystem }:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "harvest-rounder";
  version = "0.1.0";
  src = ../../packages/harvest;

  pyproject = true;
  build-system = [ pkgs.python3.pkgs.hatchling ];

  doCheck = false;

  dependencies = [
    pkgs.python3.pkgs.rich
    perSystem.self.rest
    perSystem.self.transferwise
  ];
}
