{ pkgs, perSystem }:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "sevdesk-cli";
  version = "0.1.0";
  pyproject = true;

  src = ../../packages/sevdesk-cli;

  build-system = [ pkgs.python3.pkgs.hatchling ];

  dependencies = [
    perSystem.self.sevdesk-api
  ];

  pythonImportsCheck = [ "sevdesk_cli" ];

  meta = with pkgs.lib; {
    description = "Command line interface for SevDesk API";
    license = licenses.mit;
    maintainers = [ ];
  };
}
