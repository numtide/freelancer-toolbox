{ pkgs, perSystem }:
pkgs.mkShell {
  shellHook = ''
    export PATH=$PATH:$(pwd)/bin
  '';
  packages =
    perSystem.self.harvest-exporter.nativeBuildInputs
    ++ perSystem.self.quipu-invoicer.nativeBuildInputs
    ++ [
      perSystem.self.formatter
      pkgs.python3Packages.rsa
      pkgs.texlive.combined.scheme-small
      pkgs.pandoc
      pkgs.ruff
    ];
  propagatedBuildInputs =
    perSystem.self.harvest-exporter.propagatedBuildInputs
    ++ perSystem.self.quipu-invoicer.propagatedBuildInputs;
  dontUseSetuptoolsShellHook = 1;
}
