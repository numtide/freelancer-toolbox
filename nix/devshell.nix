{ pkgs, perSystem }:
pkgs.mkShell {
  packages =
    perSystem.self.harvest-exporter.nativeBuildInputs
    ++ perSystem.self.quipu-invoicer.nativeBuildInputs
    ++ [
      perSystem.self.formatter
      pkgs.python3Packages.rsa
      pkgs.ruff
      pkgs.uv
    ];
  propagatedBuildInputs =
    perSystem.self.harvest-exporter.propagatedBuildInputs
    ++ perSystem.self.quipu-invoicer.propagatedBuildInputs;
  dontUseSetuptoolsShellHook = 1;
}
