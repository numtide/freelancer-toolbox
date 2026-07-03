{ pkgs }:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "paperless-cli";
  version = "0.1.0";

  src = ../../packages/paperless-cli;

  pyproject = true;

  build-system = with pkgs.python3.pkgs; [
    hatchling
  ];

  pythonImportsCheck = [ "paperless_cli" ];

  meta = with pkgs.lib; {
    description = "CLI tool for managing Paperless-ngx documents, mail accounts, and rules";
    license = licenses.mit;
    maintainers = [ ];
    mainProgram = "paperless-cli";
  };
}
