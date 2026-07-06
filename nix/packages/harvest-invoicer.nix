{ pkgs, perSystem }:
pkgs.python3.pkgs.buildPythonApplication {
  pname = "harvest-invoicer";
  version = "0.1.0";
  src = ../../packages/harvest-invoicer;

  pyproject = true;
  build-system = [ pkgs.python3.pkgs.hatchling ];

  dependencies = with pkgs.python3.pkgs; [
    (pkgs.python3.pkgs.toPythonModule perSystem.self.harvest-exporter)
    flask
    jinja2
    weasyprint
    click
  ];

  # Unset any ambient PYTHONPATH so Python 3.12 site-packages from a co-active
  # nix develop shell (e.g. the ecbx worktree) cannot pollute the 3.13 closure.
  makeWrapperArgs = [
    "--unset"
    "PYTHONPATH"
  ];

  # Run the full pytest suite as part of the build, so `nix flake check`
  # gates on it (blueprint surfaces package builds as checks).  The
  # WeasyPrint-dependent tests use their own env-guard and simply skip if
  # the native libraries are ever unavailable in the sandbox.
  doCheck = true;
  nativeCheckInputs = [ pkgs.python3.pkgs.pytestCheckHook ];

  meta.mainProgram = "harvest-invoicer";
}
