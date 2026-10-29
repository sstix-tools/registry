{
  description = "sstix-tools utility registry";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    "example-tool".url = "github:sstix-tools/example-tool";
    "example-tool".inputs.nixpkgs.follows = "nixpkgs";
    "git-clone-remote".url = "github:sstix-tools/git-clone-remote";
    "git-clone-remote".inputs.nixpkgs.follows = "nixpkgs";
    "project".url = "github:sstix-tools/project";
    "project".inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs, ... }@inputs:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "x86_64-linux"
        "aarch64-linux"
      ];

      forAllSystems = f:
        nixpkgs.lib.genAttrs systems (system: f system nixpkgs.legacyPackages.${system});

    in {
      packages = forAllSystems (system: pkgs: {
        "example-tool" = inputs."example-tool".packages.${system}.default or inputs."example-tool".packages.${system}."example-tool" or null;
        "git-clone-remote" = inputs."git-clone-remote".packages.${system}.default or inputs."git-clone-remote".packages.${system}."git-clone-remote" or null;
        "project" = inputs."project".packages.${system}.default or inputs."project".packages.${system}."project" or null;
      });

      legacyPackages = forAllSystems (system: pkgs: self.packages.${system});

      apps = forAllSystems (system: pkgs: {
        "example-tool" = inputs."example-tool".apps.${system}.default or { type = "app"; program = "${self.packages.${system}."example-tool"}/bin/example-tool"; };
        "git-clone-remote" = inputs."git-clone-remote".apps.${system}.default or { type = "app"; program = "${self.packages.${system}."git-clone-remote"}/bin/git-clone-remote"; };
        "project" = inputs."project".apps.${system}.default or { type = "app"; program = "${self.packages.${system}."project"}/bin/project"; };
      });

      overlays.default = final: prev: {
        "example-tool" = inputs."example-tool".packages.${final.system}.default or inputs."example-tool".packages.${final.system}."example-tool" or null;
        "git-clone-remote" = inputs."git-clone-remote".packages.${final.system}.default or inputs."git-clone-remote".packages.${final.system}."git-clone-remote" or null;
        "project" = inputs."project".packages.${final.system}.default or inputs."project".packages.${final.system}."project" or null;
      };

      overlay = self.overlays.default;
    };
}
