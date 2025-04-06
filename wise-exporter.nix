{ pkgs ? import <nixpkgs> { } }:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "wise-exporter";
  version = "0.0.1";
  src = ./wise-exporter;
  propagatedBuildInputs = [
    pkgs.python3.pkgs.rsa
  ];

  doCheck = false;
}
