{ lib
, python3
}:

python3.pkgs.buildPythonPackage {
  pname = "sevdesk-api";
  version = "0.1.0";
  pyproject = true;

  src = ./.;

  nativeBuildInputs = with python3.pkgs; [
    setuptools
    wheel
  ];

  # No runtime dependencies for the base API client
  propagatedBuildInputs = [ ];

  # Optional development dependencies
  passthru.optional-dependencies = with python3.pkgs; {
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
