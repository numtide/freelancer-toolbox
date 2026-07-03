{ pkgs, perSystem }:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "sevdesk-invoicer";
  version = "0.1.0";
  src = ../../packages/sevdesk-invoicer;
  pyproject = true;
  build-system = [
    pkgs.python3.pkgs.hatchling
  ];

  dependencies = [
    perSystem.self.sevdesk-api
  ];

  doCheck = false;
}
