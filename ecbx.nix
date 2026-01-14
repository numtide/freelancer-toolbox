{ pkgs ? import <nixpkgs> { } }:
let
  inherit (pkgs) lib python3;

  python3Packages = python3.pkgs;

  pyproject = builtins.fromTOML (builtins.readFile ./ecbx/pyproject.toml);

  parseDependency = dep:
    let
      parts = lib.splitString "[" dep;
      name = lib.head parts;
      extras =
        lib.optionals (lib.length parts > 1)
          (lib.splitString "," (lib.removeSuffix "]" (builtins.elemAt parts 1)));
    in
    {
      inherit name;
      inherit extras;
    };

  resolvePackages = dep:
    let
      inherit (parseDependency dep) name extras;
      package = python3Packages.${name};
      optionalPackages = lib.flatten (map (name: package.optional-dependencies.${name}) extras);
    in
    [ package ] ++ optionalPackages;
in
python3Packages.buildPythonApplication rec {
  pname = "ecbx";
  version = pyproject.project.version;
  pyproject = true;

  src = lib.cleanSource ./ecbx;

  nativeBuildInputs =
    (with python3Packages; [setuptools]) ++
    map (name: python3Packages.${name}) pyproject.build-system.requires;

  propagatedBuildInputs = lib.flatten (map resolvePackages pyproject.project.dependencies);

  doCheck = false;

  meta.mainProgram = pname;
}
