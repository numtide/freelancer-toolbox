{ pkgs ? import <nixpkgs> { } }:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "harvest-exporter";
  version = "0.0.1";
  src = ./.;

  doCheck = false;

  propagatedBuildInputs = [ pkgs.python3.pkgs.rich ];
}
