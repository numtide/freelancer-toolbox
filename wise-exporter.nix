{
  pkgs ? import <nixpkgs> { },
}:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "wise-exporter";
  version = "0.0.1";
  src = ./wise-exporter;

  pyproject = true;
  build-system = [ pkgs.python3.pkgs.setuptools ];

  dependencies = [
    pkgs.python3.pkgs.rsa
  ];

  doCheck = false;
}
