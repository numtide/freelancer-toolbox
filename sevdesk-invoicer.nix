{
  hatchling,
  buildPythonApplication,
  sevdesk-api,
}:
buildPythonApplication {
  pname = "sevdesk-invoicer";
  version = "0.0.1";
  src = ./sevdesk-invoicer;
  pyproject = true;
  nativeBuildInputs = [
    hatchling
  ];

  propagatedBuildInputs = [
    sevdesk-api
  ];

  doCheck = false;
}
