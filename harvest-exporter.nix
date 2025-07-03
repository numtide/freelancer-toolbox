{ pkgs ? import <nixpkgs> { } }:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "harvest-exporter";
  version = "0.0.1";
  src = ./.;

  pyproject = true;
  build-system = [ pkgs.python3.pkgs.setuptools ];

  doCheck = false;

  dependencies = [ pkgs.python3.pkgs.rich ];
}
