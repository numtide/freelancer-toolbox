{
  pkgs,
  inputs,
  flake,
  perSystem,
}:
let
  treefmtEval = inputs.treefmt-nix.lib.evalModule pkgs (
    import ./treefmt.nix { inherit pkgs perSystem; }
  );
  inherit (treefmtEval.config.build) wrapper;
in
# Blueprint exposes the formatter as a package, so attaching the treefmt
# check as a passthru test surfaces it in `nix flake check` as
# checks.<system>.pkgs-formatter-check.
wrapper
// {
  passthru = (wrapper.passthru or { }) // {
    tests.check = treefmtEval.config.build.check flake;
  };
}
