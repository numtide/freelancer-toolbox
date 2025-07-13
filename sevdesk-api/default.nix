{
  lib,
  python,
}:

python.pkgs.buildPythonPackage {
  pname = "sevdesk-api";
  version = "0.1.0";
  pyproject = true;

  src = ./.;

  nativeBuildInputs = with python.pkgs; [
    hatchling
  ];

  # No runtime dependencies for the base API client
  propagatedBuildInputs = [ ];

  # Optional development dependencies
  passthru.optional-dependencies = with python.pkgs; {
    dev = [
      black
      ruff
      mypy
      pytest
    ];
  };

  pythonImportsCheck = [ "sevdesk_api" ];

  meta = with lib; {
    description = "Python client for the sevDesk API";
    homepage = "https://github.com/numtide/freelancer-toolbox";
    license = licenses.mit;
    maintainers = [ ];
  };
}
