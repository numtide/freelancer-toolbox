{ pkgs }:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "ecbx";
  version = "0.1.0";
  src = ../../packages/ecbx;
  pyproject = true;
  build-system = [ pkgs.python3.pkgs.hatchling ];
  dependencies = with pkgs.python3.pkgs; [
    requests
    click
    rich
  ];
  doCheck = false;
  meta.mainProgram = "ecbx";
}
