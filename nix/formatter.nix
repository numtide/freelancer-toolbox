{
  pkgs,
  inputs,
  perSystem,
}:
(inputs.treefmt-nix.lib.evalModule pkgs (import ./treefmt.nix { inherit pkgs perSystem; }))
  .config.build.wrapper
