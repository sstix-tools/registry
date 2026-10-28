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
      });
    };
}
