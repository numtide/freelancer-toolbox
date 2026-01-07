{ pkgs ? import <nixpkgs> { } }: let
  pyproject = builtins.fromTOML (builtins.readFile ./ecbx/pyproject.toml);

  parseDependency = dep: let
    parts = lib.splitString "[" dep;
    name = lib.head parts;
    extras =
      lib.optionals (lib.length parts > 1)
      (lib.splitString "," (lib.removeSuffix "]" (builtins.elemAt parts 1)));
  in {
    inherit name;
    inherit extras;
  };

  # { name: str, extras: [str] } -> [package]
  resolvePackages = dep: let
    inherit (parseDependency dep) name extras;
    package = python3Packages.${name};
    optionalPackages = lib.flatten (map (name: package.optional-dependencies.${name}) extras);
  in
    [package] ++ optionalPackages;
in
pkgs.python3.pkgs.buildPythonApplication rec {
  pname = "ecbx";
  inherit (pyproject.project) version;
  pyproject = true;

  src = ./ecbx;

  nativeBuildInputs =
        map (name: python3Packages.${name}) pyproject.build-system.requires
        ++ [
         python3Packages.setuptools
        ];

      propagatedBuildInputs = lib.flatten (map resolvePackages pyproject.project.dependencies);

  doCheck = false;

  meta.mainProgram = pname;
}
