{
  lib,
  buildPythonApplication,
  hatchling,
  sevdesk-api,
}:

buildPythonApplication {
  pname = "sevdesk-cli";
  version = "0.1.0";
  pyproject = true;

  src = ./.;

  build-system = [ hatchling ];

  dependencies = [
    sevdesk-api
  ];

  pythonImportsCheck = [ "sevdesk_cli" ];

  meta = with lib; {
    description = "Command line interface for SevDesk API";
    license = licenses.mit;
    maintainers = [ ];
  };
}
