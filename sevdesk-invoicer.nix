{
  setuptools,
  buildPythonApplication,
  sevdesk-api,
}:
buildPythonApplication {
  pname = "sevdesk-invoicer";
  version = "0.0.1";
  src = ./sevdesk-invoicer;
  pyproject = true;
  nativeBuildInputs = [
    setuptools
  ];

  propagatedBuildInputs = [
    sevdesk-api
  ];

  doCheck = false;
}
