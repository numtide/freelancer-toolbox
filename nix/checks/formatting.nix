{
  pkgs,
  inputs,
  flake,
  perSystem,
  ...
}:
(inputs.treefmt-nix.lib.evalModule pkgs (import ../treefmt.nix { inherit pkgs perSystem; }))
.config.build.check
  flake
