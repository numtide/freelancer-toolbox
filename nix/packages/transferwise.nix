{ pkgs, rest }:
let
  inherit (pkgs) lib python3;
in
python3.pkgs.buildPythonPackage {
  pname = "transferwise";
  version = "0.1.0";
  pyproject = true;

  src = ../../packages/transferwise;

  build-system = with python3.pkgs; [
    hatchling
  ];

  dependencies = [ rest ];

  pythonImportsCheck = [ "transferwise" ];

  meta = with lib; {
    description = "Wise (TransferWise) exchange-rate client used by Numtide freelancer-toolbox exporters";
    homepage = "https://github.com/numtide/freelancer-toolbox";
    license = licenses.mit;
    maintainers = [ ];
  };
}
