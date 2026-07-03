{ pkgs }:
pkgs.python3.pkgs.buildPythonApplication rec {
  pname = "quipu-invoicer";
  inherit
    ((builtins.fromTOML (builtins.readFile ../../packages/quipu-invoicer/pyproject.toml)).project)
    version
    ;
  pyproject = true;

  src = ../../packages/quipu-invoicer;

  build-system = [
    pkgs.python3.pkgs.hatchling
  ];

  dependencies = with pkgs.python3.pkgs; [
    click
    click-option-group
    requests
  ];

  doCheck = false;

  meta.mainProgram = pname;
}
