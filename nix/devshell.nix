{
  pkgs,
  toolbox,
  formatter,
}:
pkgs.mkShell {
  packages =
    toolbox.harvest-exporter.nativeBuildInputs
    ++ toolbox.quipu-invoicer.nativeBuildInputs
    ++ [
      formatter
      pkgs.python3Packages.rsa
      pkgs.ruff
      pkgs.uv
    ];
  propagatedBuildInputs =
    toolbox.harvest-exporter.propagatedBuildInputs ++ toolbox.quipu-invoicer.propagatedBuildInputs;
  dontUseSetuptoolsShellHook = 1;
}
