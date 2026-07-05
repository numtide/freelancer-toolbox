{ pkgs }:
let
  inherit (pkgs) lib python3;
in
python3.pkgs.buildPythonPackage {
  pname = "rest";
  version = "0.1.0";
  pyproject = true;

  src = ../../packages/rest;

  build-system = with python3.pkgs; [
    hatchling
  ];

  dependencies = [ ];

  pythonImportsCheck = [ "rest" ];

  meta = with lib; {
    description = "Minimal HTTP helper used by Numtide freelancer-toolbox clients";
    homepage = "https://github.com/numtide/freelancer-toolbox";
    license = licenses.mit;
    maintainers = [ ];
  };
}
