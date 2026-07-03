{ pkgs }:
pkgs.writers.writePython3Bin "working-days-calculator" {
  libraries = [ pkgs.python3Packages.pandas ];
  flakeIgnore = [ "E501" ];
} (builtins.readFile ../../working-days-calculator.py)
