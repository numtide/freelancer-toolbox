# treefmt-nix module config, evaluated in flake.nix.
{ pkgs, toolbox }:
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
        extraPythonPackages = [ toolbox.rest ];
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
        ];
        extraPythonPackages = [
          toolbox.rest
          toolbox.transferwise
          pkgs.python3.pkgs.rich
        ];
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
      "packages/kimai" = {
        modules = [
          "src/kimai"
          "src/kimai_exporter"
        ];
        extraPythonPackages = [
          toolbox.rest
          toolbox.transferwise
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
        extraPythonPackages = [ toolbox.sevdesk-api ];
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
      "packages/harvest-invoicer" = {
        modules = [ "src/harvest_invoicer" ];
        extraPythonPackages = with pkgs.python3.pkgs; [
          (pkgs.python3.pkgs.toPythonModule toolbox.harvest-exporter)
          flask
          click
          jinja2
          pydantic
          pydantic-settings
        ];
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
      "packages/working-days-calculator" = {
        modules = [ "src/working_days_calculator" ];
        extraPythonPackages = with pkgs.python3.pkgs; [
          pandas
          pandas-stubs
        ];
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
      "packages/sevdesk-cli" = {
        modules = [ "src/sevdesk_cli" ];
        extraPythonPackages = [ toolbox.sevdesk-api ];
        options = [
          "--config-file"
          "../../pyproject.toml"
        ];
      };
      "packages/ecbx" = {
        modules = [ "src/ecbx" ];
        extraPythonPackages = with pkgs.python3.pkgs; [
          click
          rich
          types-requests
        ];
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
