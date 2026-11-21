self:
{ config, lib, pkgs, ... }:

let
  cfg = config.programs.seep-reverse-lab;
  skillRoot = "${cfg.package}/share/seep-reverse-lab/Tool/skill";

  regularSkills = [
    "apkseep"
    "client-license-validation-bypass"
    "exe-reverse"
    "softseep"
    "webseep"
  ];

  safeSkills = [
    "apk-reverse"
    "ida-reverse"
    "mcp-js-reverse-playbook"
    "radare2"
    "reverse-engineering"
  ];

  regularSkillFiles = lib.listToAttrs (map (name: {
    name = "${cfg.skills.targetDirectory}/${name}";
    value = {
      source = "${skillRoot}/${name}";
    };
  }) regularSkills);

  safeSkillFiles = lib.listToAttrs (map (name: {
    name = "${cfg.skills.targetDirectory}/${name}";
    value = {
      source = "${skillRoot}/safe-skills/${name}";
    };
  }) safeSkills);

  androidSdk = pkgs.androidenv.composeAndroidPackages {
    platformVersions = [ cfg.optionalTools.androidSdk.platformVersion ];
    buildToolsVersions = [ cfg.optionalTools.androidSdk.buildToolsVersion ];
    includeEmulator = false;
    includeSystemImages = false;
    includeSources = false;
  };

  optionalPackages =
    lib.optional cfg.optionalTools.androidTools pkgs.android-tools
    ++ lib.optional cfg.optionalTools.frida pkgs.frida-tools
    ++ lib.optional cfg.optionalTools.ghidra pkgs.ghidra
    ++ lib.optional cfg.optionalTools.androidSdk.enable androidSdk.androidsdk;
in
{
  options.programs.seep-reverse-lab = {
    enable = lib.mkEnableOption "Seep Reverse Lab MCP workbench";

    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      defaultText = lib.literalExpression "seep-reverse-lab.packages.${pkgs.system}.default";
      description = "Seep Reverse Lab package to install and use as the skill source.";
    };

    installPackage = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Whether to add the Seep Reverse Lab package, including seep-mcp, to home.packages.";
    };

    skills = {
      enable = lib.mkEnableOption "Seep Reverse Lab skills" // { default = true; };

      targetDirectory = lib.mkOption {
        type = lib.types.str;
        default = ".pi/agent/skills";
        description = "Home-relative directory where Pi discovers skills.";
      };
    };

    mcp.enable = lib.mkEnableOption "the Seep entry in the shared MCP server registry" // { default = true; };

    optionalTools = {
      androidTools = lib.mkEnableOption "ADB, Fastboot, and other Android platform tools";
      frida = lib.mkEnableOption "Frida host-side dynamic instrumentation tools";
      ghidra = lib.mkEnableOption "Ghidra and its headless analysis tools";

      androidSdk = {
        enable = lib.mkEnableOption "Android SDK Build Tools such as apksigner, zipalign, aapt2, and d8";

        platformVersion = lib.mkOption {
          type = lib.types.str;
          default = "35";
          description = "Android SDK platform version to install.";
        };

        buildToolsVersion = lib.mkOption {
          type = lib.types.str;
          default = "35.0.0";
          description = "Android SDK Build Tools version to install.";
        };
      };
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = lib.optional cfg.installPackage cfg.package ++ optionalPackages;

    home.file = lib.mkIf cfg.skills.enable (
      regularSkillFiles // safeSkillFiles
    );

    programs.mcp = lib.mkIf cfg.mcp.enable {
      enable = true;
      servers.seep = {
        command = "${cfg.package}/bin/seep-mcp";
        args = [ ];
      };
    };

    home.sessionVariables = lib.optionalAttrs cfg.optionalTools.androidSdk.enable {
      ANDROID_HOME = "${androidSdk.androidsdk}/libexec/android-sdk";
      ANDROID_SDK_ROOT = "${androidSdk.androidsdk}/libexec/android-sdk";
    };

    warnings = lib.optional cfg.optionalTools.androidSdk.enable ''
      programs.seep-reverse-lab.optionalTools.androidSdk.enable requires the
      Android SDK license to be accepted through nixpkgs configuration:
      nixpkgs.config.android_sdk.accept_license = true;
      The Android SDK packages are also unfree, so allowUnfree or a matching
      allowUnfreePredicate must be configured by the importing system.
    '';
  };
}
