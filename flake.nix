{
  description = "Seep Reverse Lab - NixOS package, MCP server, and development shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    {
      homeManagerModules = {
        default = import ./nix/home-manager.nix self;
        seep-reverse-lab = self.homeManagerModules.default;
      };
    }
    // flake-utils.lib.eachSystem [ "x86_64-linux" ] (system:
      let
        pkgs = import nixpkgs { inherit system; };

        python = pkgs.python3.withPackages (ps: [ ps.mcp ]);

        runtimePath = pkgs.lib.makeBinPath [
          pkgs.radare2
          pkgs.jdk17
          pkgs.jadx
          pkgs.apktool
          pkgs.nodejs
          pkgs.unzip
        ];

        seep-reverse-lab = pkgs.stdenvNoCC.mkDerivation {
          pname = "seep-reverse-lab";
          version = builtins.replaceStrings [ "\n" ] [ "" ] (builtins.readFile ./VERSION);
          src = ./.;

          nativeBuildInputs = [ pkgs.makeWrapper ];

          installPhase = ''
            runHook preInstall

            mkdir -p "$out/share/seep-reverse-lab" "$out/bin"
            cp -r . "$out/share/seep-reverse-lab/"

            # The server resolves these bundled paths before consulting PATH.
            # Replace the launchers with Nix packages so their interpreters and
            # native dependencies work without an FHS compatibility layer.
            ln -sf ${pkgs.jadx}/bin/jadx \
              "$out/share/seep-reverse-lab/Tool/mcp/Tool/safe/jadx/bin/jadx"
            ln -sf ${pkgs.apktool}/libexec/apktool/apktool.jar \
              "$out/share/seep-reverse-lab/Tool/mcp/Tool/safe/apktool/apktool.jar"

            makeWrapper ${python}/bin/python "$out/bin/seep-reverse-lab" \
              --add-flags "$out/share/seep-reverse-lab/Tool/mcp/seep_mcp_server.py" \
              --prefix PATH : ${runtimePath} \
              --set-default JAVA_HOME ${pkgs.jdk17}

            makeWrapper ${python}/bin/python "$out/bin/seep-mcp" \
              --add-flags "$out/share/seep-reverse-lab/Tool/mcp/seep_mcp_server.py" \
              --prefix PATH : ${runtimePath} \
              --set-default JAVA_HOME ${pkgs.jdk17}

            runHook postInstall
          '';

          meta = {
            description = "Agent-native reverse engineering and security analysis MCP workbench";
            homepage = "https://github.com/angusdevgo/Seep-Reverse-Lab";
            license = pkgs.lib.licenses.gpl3Plus;
            mainProgram = "seep-reverse-lab";
            platforms = [ "x86_64-linux" ];
          };
        };
      in {
        packages = {
          default = seep-reverse-lab;
          inherit seep-reverse-lab;
        };

        apps = {
          default = {
            type = "app";
            program = "${seep-reverse-lab}/bin/seep-reverse-lab";
            meta = seep-reverse-lab.meta;
          };
          seep-mcp = {
            type = "app";
            program = "${seep-reverse-lab}/bin/seep-mcp";
            meta = seep-reverse-lab.meta;
          };
        };

        checks.default = pkgs.runCommand "seep-reverse-lab-check" {
          nativeBuildInputs = [ python pkgs.jdk17 ];
        } ''
          export HOME="$TMPDIR/home"
          mkdir -p "$HOME"
          python ${./nix/check-package.py} ${seep-reverse-lab}
          touch "$out"
        '';

        devShells.default = pkgs.mkShell {
          packages = [
            python
            pkgs.radare2
            pkgs.jdk17
            pkgs.jadx
            pkgs.apktool
            pkgs.nodejs
            pkgs.unzip
          ];

          JAVA_HOME = "${pkgs.jdk17}";

          shellHook = ''
            echo "Seep Reverse Lab development environment"
            echo "Run the MCP server with: python Tool/mcp/seep_mcp_server.py"
          '';
        };
      });
}
