{ pkgs ? import <nixpkgs> { }, treefmt ? null }:
let
  harvest-exporter = pkgs.callPackage ./harvest-exporter.nix { };
  sevdesk-invoicer = pkgs.callPackage ./sevdesk-invoicer.nix { };
  quipu-invoicer = pkgs.callPackage ./quipu-invoicer.nix { };
in
pkgs.mkShell {
  shellHook = ''
    export PATH=$PATH:$(pwd)/bin
  '';
  packages = sevdesk-invoicer.nativeBuildInputs
    ++ harvest-exporter.nativeBuildInputs
    ++ quipu-invoicer.nativeBuildInputs
    ++ pkgs.lib.optional (treefmt != null) treefmt
    ++ [
    pkgs.python3Packages.rsa
    pkgs.texlive.combined.scheme-small
    pkgs.pandoc
    pkgs.ruff
  ];
  propagatedBuildInputs = sevdesk-invoicer.propagatedBuildInputs ++ harvest-exporter.propagatedBuildInputs ++ quipu-invoicer.propagatedBuildInputs;
  dontUseSetuptoolsShellHook = 1;
}
