{
  pkgs ? import <nixpkgs> { },
}:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "sevdesk-invoicer";
  version = "0.0.1";
  src = ./sevdesk-invoicer;
  pyproject = true;
  nativeBuildInputs = [
    pkgs.python3.pkgs.setuptools
  ];

  doCheck = false;
}
