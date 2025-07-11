{
  pkgs ? import <nixpkgs> { },
}:
pkgs.python3.pkgs.buildPythonApplication rec {
  pname = "quipu-invoicer";
  inherit ((builtins.fromTOML (builtins.readFile ./quipu/pyproject.toml)).project) version;
  pyproject = true;

  src = ./quipu;

  propagatedBuildInputs = with pkgs.python3.pkgs; [
    click
    click-option-group
  ];

  nativeBuildInputs = [
    pkgs.python3.pkgs.setuptools
  ];

  doCheck = false;

  meta.mainProgram = pname;
}
