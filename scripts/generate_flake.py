#!/usr/bin/env python3

import json
import os
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGES_FILE = ROOT / "registry" / "packages.json"

ORG = os.getenv("TOOLS_ORG", "sstix-tools")

# Flake output destinations
ROOT_FLAKE_FILE = ROOT / "flake.nix"
PAGES_DIR = ROOT / "site" / "nix"
PAGES_FLAKE_FILE = PAGES_DIR / "flake.nix"
SITE_FLAKE_FILE = ROOT / "site" / "flake.nix"


def nix_ident(name: str) -> str:
    """
    Ensure a safe identifier for Nix attribute names.
    """
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def main():
    if not PACKAGES_FILE.exists():
        packages = []
    else:
        try:
            packages = json.loads(PACKAGES_FILE.read_text(encoding="utf-8"))
        except Exception:
            packages = []

    # Collect unique repositories across packages
    repos = {}
    for item in packages:
        repo = item.get("repository", item.get("name"))
        pkg_name = item.get("name", repo)
        repos[repo] = {
            "name": pkg_name,
            "repo": repo,
            "tag": item.get("tag"),
        }

    lines = [
        "{",
        '  description = "sstix-tools utility registry";',
        "",
        "  inputs = {",
        '    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";',
    ]

    for repo, data in repos.items():
        var_name = nix_ident(repo)
        lines.append(f'    "{var_name}".url = "github:{ORG}/{repo}";')
        lines.append(f'    "{var_name}".inputs.nixpkgs.follows = "nixpkgs";')

    lines.extend([
        "  };",
        "",
        "  outputs = { self, nixpkgs, ... }@inputs:",
        "    let",
        "      systems = [",
        '        "aarch64-darwin"',
        '        "x86_64-darwin"',
        '        "x86_64-linux"',
        '        "aarch64-linux"',
        "      ];",
        "",
        "      forAllSystems = f:",
        "        nixpkgs.lib.genAttrs systems (system: f system nixpkgs.legacyPackages.${system});",
        "",
        "    in {",
        "      packages = forAllSystems (system: pkgs: {",
    ])

    for repo, data in repos.items():
        var_name = nix_ident(repo)
        pkg_name = data["name"]
        lines.append(
            f'        "{pkg_name}" = inputs."{var_name}".packages.${{system}}.default or inputs."{var_name}".packages.${{system}}."{pkg_name}" or null;'
        )

    lines.extend([
        "      });",
        "",
        "      legacyPackages = forAllSystems (system: pkgs: self.packages.${system});",
        "",
        "      apps = forAllSystems (system: pkgs: {",
    ])

    for repo, data in repos.items():
        var_name = nix_ident(repo)
        pkg_name = data["name"]
        lines.append(
            f'        "{pkg_name}" = inputs."{var_name}".apps.${{system}}.default or {{ type = "app"; program = "${{self.packages.${{system}}."{pkg_name}"}}/bin/{pkg_name}"; }};'
        )

    lines.extend([
        "      });",
        "",
        "      overlays.default = final: prev: {",
    ])

    for repo, data in repos.items():
        var_name = nix_ident(repo)
        pkg_name = data["name"]
        lines.append(
            f'        "{pkg_name}" = inputs."{var_name}".packages.${{final.system}}.default or inputs."{var_name}".packages.${{final.system}}."{pkg_name}" or null;'
        )

    lines.extend([
        "      };",
        "",
        "      overlay = self.overlays.default;",
        "    };",
        "}",
        "",
    ])

    flake_content = "\n".join(lines)

    ROOT_FLAKE_FILE.write_text(flake_content, encoding="utf-8")
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_FLAKE_FILE.write_text(flake_content, encoding="utf-8")
    SITE_FLAKE_FILE.write_text(flake_content, encoding="utf-8")

    print(f"Wrote {ROOT_FLAKE_FILE}")
    print(f"Wrote {PAGES_FLAKE_FILE}")
    print(f"Wrote {SITE_FLAKE_FILE}")


if __name__ == "__main__":
    main()
