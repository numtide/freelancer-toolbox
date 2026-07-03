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
        options = [
          "--config-file"
          "../../pyproject.toml"
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
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
      "packages/sevdesk-api" = {
        modules = [ "sevdesk_api" ];
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
      "packages/sevdesk-invoicer" = {
        modules = [
          "sevdesk_invoicer"
          "sevdesk_wise_importer"
          "sevdesk_tax_estimator"
        ];
        extraPythonPackages = [ perSystem.self.sevdesk-api ];
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
      "packages/wise-exporter" = {
        extraPythonPackages = [ pkgs.python3.pkgs.rsa ];
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
      "packages/paperless-cli" = {
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
      "packages/sevdesk-cli" = {
        modules = [ "sevdesk_cli" ];
        extraPythonPackages = [ perSystem.self.sevdesk-api ];
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
    };
  };

  programs.ruff-check.enable = true;
  programs.ruff-format.enable = true;
  programs.nixfmt.enable = true;
  programs.deadnix.enable = true;
  programs.statix.enable = true;
}
