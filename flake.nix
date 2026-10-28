{
  description = "sstix-tools utility registry";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "x86_64-linux"
        "aarch64-linux"
      ];

      forAllSystems = function:
        nixpkgs.lib.genAttrs systems (system:
          function system nixpkgs.legacyPackages.${system}
        );

    in {
      packages = forAllSystems (system: pkgs: {
        example-tool = pkgs.stdenvNoCC.mkDerivation {
          pname = "example-tool";
          version = "1.0.3";

          src = pkgs.fetchurl {
            url = "https://github.com/sstix-tools/example-tool/releases/download/v1.0.3/example-tool-1.0.3.tar.gz";
            hash = "sha256-SJw0QdWAbc8cwgypGCHPMdFFd3aYu4A3j0LaSb6cUD4=";
          };

          nativeBuildInputs = [
            pkgs.makeWrapper
          ];

          installPhase = ''
            mkdir -p $out/bin $out/share/zsh/site-functions
            install -D -m 0755 example-tool-1.0.3/bin/example-tool $out/bin/example-tool
            wrapProgram $out/bin/example-tool \
              --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.coreutils ]}
            if [ -d example-tool-1.0.3/completion ]; then
              cp -r example-tool-1.0.3/completion/* $out/share/zsh/site-functions/ 2>/dev/null || true
            fi
          '';

          meta = {
            platforms = pkgs.lib.platforms.unix;
            mainProgram = "example-tool";
            description = "example-tool from sstix-tools";
          };
        };

      });
    };
}
