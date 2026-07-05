{ pkgs }:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "working-days-calculator";
  version = "0.1.0";

  src = ../../packages/working-days-calculator;

  pyproject = true;

  build-system = [ pkgs.python3.pkgs.hatchling ];

  dependencies = [
    pkgs.python3.pkgs.pandas
  ];

  doCheck = false;

  meta = with pkgs.lib; {
    description = "Calculate working days from a Harvest time report CSV";
    license = licenses.mit;
    maintainers = [ ];
    mainProgram = "working-days-calculator";
  };
}
