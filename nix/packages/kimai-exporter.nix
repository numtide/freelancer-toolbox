{ pkgs, perSystem }:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "kimai-exporter";
  version = "0.1.0";
  src = ../../packages/kimai;

  pyproject = true;
  build-system = [ pkgs.python3.pkgs.hatchling ];

  dependencies = [
    perSystem.self.rest
    perSystem.self.transferwise
  ];

  doCheck = false;

  meta.mainProgram = "kimai-exporter";
}
