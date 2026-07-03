# treefmt-nix module config, evaluated by formatter.nix.
# Not part of blueprint's folder mapping.
{ pkgs, perSystem }:
{
  # Used to find the project root
  projectRootFile = "flake.lock";

  programs.mypy = {
    enable = true;
    directories = {
      "packages/harvest" = {
        modules = [
          "harvest"
          "harvest_exporter"
          "harvest_rounder"
          "kimai"
          "kimai_exporter"
          "rest"
        ];
      };
      "packages/quipu-invoicer" = {
        modules = [
          "quipu_api"
          "quipu_invoicer"
        ];
        extraPythonPackages = with pkgs.python3.pkgs; [
          click
          click-option-group
          types-requests
        ];
      };
      "packages/sevdesk-api" = {
        modules = [ "sevdesk_api" ];
      };
      "packages/sevdesk-invoicer" = {
        modules = [
          "sevdesk_invoicer"
          "sevdesk_wise_importer"
          "sevdesk_tax_estimator"
        ];
        extraPythonPackages = [ perSystem.self.sevdesk-api ];
      };
      "packages/wise-exporter" = {
        extraPythonPackages = [ pkgs.python3.pkgs.rsa ];
      };
      "packages/paperless-cli" = { };
      "packages/sevdesk-cli" = {
        modules = [ "sevdesk_cli" ];
        extraPythonPackages = [ perSystem.self.sevdesk-api ];
      };
    };
  };

  programs.ruff-check.enable = true;
  programs.ruff-format.enable = true;
  programs.nixfmt.enable = true;
  programs.deadnix.enable = true;
  programs.statix.enable = true;
}
