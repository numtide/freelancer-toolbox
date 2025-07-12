{
  lib,
  buildPythonApplication,
  setuptools,
  sevdesk-api,
}:

buildPythonApplication {
  pname = "sevdesk-cli";
  version = "0.1.0";
  pyproject = true;

  src = ./.;

  build-system = [ setuptools ];

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
