# Custom package scope for the toolbox. Every sibling *.nix file becomes a
# package named after its file, called with callPackage so packages can
# depend on each other by argument name.
{ lib, newScope }:
lib.makeScope newScope (
  self:
  lib.mapAttrs'
    (name: _: {
      name = lib.removeSuffix ".nix" name;
      value = self.callPackage (./. + "/${name}") { };
    })
    (
      lib.filterAttrs (
        name: type: type == "regular" && lib.hasSuffix ".nix" name && name != "default.nix"
      ) (builtins.readDir ./.)
    )
)
