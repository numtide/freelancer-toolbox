{
  description = "freelancer toolbox";

  inputs = {
    nixpkgs.url = "git+https://github.com/NixOS/nixpkgs?shallow=1&ref=nixpkgs-unstable";
    treefmt-nix.url = "github:numtide/treefmt-nix";
    treefmt-nix.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs =
    {
      self,
      nixpkgs,
      treefmt-nix,
    }:
    let
      inherit (nixpkgs) lib;
      systems = [
        "x86_64-linux"
        "aarch64-darwin"
      ];
      forAllSystems =
        f:
        lib.genAttrs systems (
          system:
          f rec {
            pkgs = nixpkgs.legacyPackages.${system};
            toolbox = pkgs.callPackage ./nix/packages { };
            treefmtEval = treefmt-nix.lib.evalModule pkgs (import ./nix/treefmt.nix { inherit pkgs toolbox; });
          }
        );
    in
    {
      packages = forAllSystems (
        { pkgs, toolbox, ... }:
        lib.filterAttrs (
          _: v: lib.isDerivation v && lib.meta.availableOn pkgs.stdenv.hostPlatform v
        ) toolbox
        // {
          default = toolbox.harvest-exporter;
        }
      );

      formatter = forAllSystems ({ treefmtEval, ... }: treefmtEval.config.build.wrapper);

      checks = forAllSystems (
        { treefmtEval, ... }@args:
        self.packages.${args.pkgs.stdenv.hostPlatform.system}
        // {
          formatting = treefmtEval.config.build.check self;
          devshell = self.devShells.${args.pkgs.stdenv.hostPlatform.system}.default;
        }
      );

      devShells = forAllSystems (
        {
          pkgs,
          toolbox,
          treefmtEval,
        }:
        {
          default = pkgs.callPackage ./nix/devshell.nix {
            inherit toolbox;
            formatter = treefmtEval.config.build.wrapper;
          };
        }
      );
    };
}
