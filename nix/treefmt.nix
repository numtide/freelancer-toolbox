# treefmt-nix module config, evaluated by formatter.nix.
# Not part of blueprint's folder mapping.
{ pkgs, perSystem }:
{
  # Used to find the project root
  projectRootFile = "flake.lock";

  programs.mypy = {
    enable = true;
    directories = {
      "packages/rest" = {
        modules = [ "src/rest" ];
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
      "packages/transferwise" = {
        modules = [ "src/transferwise" ];
        extraPythonPackages = [ perSystem.self.rest ];
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
      "packages/harvest" = {
        modules = [
          "src/harvest"
          "src/harvest_exporter"
          "src/harvest_rounder"
          "src/kimai"
          "src/kimai_exporter"
        ];
        extraPythonPackages = [
          perSystem.self.rest
          perSystem.self.transferwise
          pkgs.python3.pkgs.rich
        ];
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
      "packages/quipu-invoicer" = {
        modules = [
          "src/quipu_api"
          "src/quipu_invoicer"
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
        modules = [ "src/sevdesk_api" ];
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
      "packages/sevdesk-invoicer" = {
        modules = [
          "src/sevdesk_invoicer"
          "src/sevdesk_wise_importer"
          "src/sevdesk_tax_estimator"
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
        modules = [ "src/paperless_cli" ];
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
      "packages/sevdesk-cli" = {
        modules = [ "src/sevdesk_cli" ];
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
