#!/usr/bin/env python3

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

PACKAGES_FILE = ROOT / "registry" / "packages.json"

# This is the file that `github:sstix-tools/registry` expects.
ROOT_FLAKE_FILE = ROOT / "flake.nix"

# Optional copy for the GitHub Pages output.
PAGES_FLAKE_FILE = ROOT / "site" / "nix" / "flake.nix"


def nix_string(value):
    """
    Encode a Python string as a valid Nix string literal.
    """
    return json.dumps(str(value))


def generate_package_derivation(item):
    name = item["name"]
    version = item["version"]
    source_url = item["source_url"]
    source_hash = item["source_hash"]
    manifest = item.get("manifest", {})

    pkg_type = manifest.get("type", "utility")
    description = manifest.get("description", f"{name} from sstix-tools")
    dependencies = manifest.get("dependencies", [])
    
    # Map common dependency names to nixpkgs attribute names
    dep_map = {
        "jq": "pkgs.jq",
        "curl": "pkgs.curl",
        "python3": "pkgs.python3",
        "fzf": "pkgs.fzf",
        "git": "pkgs.git",
        "coreutils": "pkgs.coreutils",
        "findutils": "pkgs.findutils",
        "gawk": "pkgs.gawk",
        "sed": "pkgs.gnused",
        "tar": "pkgs.gnutar",
        "gzip": "pkgs.gzip",
    }
    
    nix_deps = [dep_map.get(dep, f"pkgs.{dep}") for dep in dependencies]

    lines = []
    source_directory = f"{name}-{version}"

    if pkg_type == "zsh-function":
        # Autoloadable Zsh function package
        lines.extend([
            f"        {name} = pkgs.stdenvNoCC.mkDerivation {{",
            f"          pname = {nix_string(name)};",
            f"          version = {nix_string(version)};",
            "",
            "          src = pkgs.fetchurl {",
            f"            url = {nix_string(source_url)};",
            f"            hash = {nix_string(source_hash)};",
            "          };",
            "",
            "          dontBuild = true;",
            "",
            "          installPhase = ''",
            "            mkdir -p $out/share/zsh/functions $out/share/zsh/site-functions",
            f"            if [ -d {source_directory}/functions ]; then",
            f"              cp -r {source_directory}/functions/* $out/share/zsh/functions/ 2>/dev/null || true",
            f"              cp -r {source_directory}/functions/* $out/share/zsh/site-functions/ 2>/dev/null || true",
            "            fi",
            f"            if [ -d {source_directory}/completion ]; then",
            f"              cp -r {source_directory}/completion/* $out/share/zsh/site-functions/ 2>/dev/null || true",
            "            fi",
            "          '';",
            "",
            "          meta = {",
            "            platforms = pkgs.lib.platforms.unix;",
            f"            description = {nix_string(description)};",
            "          };",
            "        };",
            "",
        ])
    elif pkg_type in ("c-utility", "compiled") or manifest.get("build_type") == "make":
        # Compiled C / C++ / Makefile utility
        lines.extend([
            f"        {name} = pkgs.stdenv.mkDerivation {{",
            f"          pname = {nix_string(name)};",
            f"          version = {nix_string(version)};",
            "",
            "          src = pkgs.fetchurl {",
            f"            url = {nix_string(source_url)};",
            f"            hash = {nix_string(source_hash)};",
            "          };",
            "",
            f"          sourceRoot = {nix_string(source_directory)};",
            "",
            "          installPhase = ''",
            "            mkdir -p $out/bin $out/share/zsh/site-functions",
            "            make install PREFIX=$out",
            "            if [ -d completion ]; then",
            "              cp -r completion/* $out/share/zsh/site-functions/ 2>/dev/null || true",
            "            fi",
            "          '';",
            "",
            "          meta = {",
            "            platforms = pkgs.lib.platforms.unix;",
            f"            mainProgram = {nix_string(name)};",
            f"            description = {nix_string(description)};",
            "          };",
            "        };",
            "",
        ])
    elif pkg_type == "python-utility":
        # Python script utility
        wrapper_deps = ["pkgs.python3"] + nix_deps
        deps_expr = " ".join(wrapper_deps)

        lines.extend([
            f"        {name} = pkgs.stdenvNoCC.mkDerivation {{",
            f"          pname = {nix_string(name)};",
            f"          version = {nix_string(version)};",
            "",
            "          src = pkgs.fetchurl {",
            f"            url = {nix_string(source_url)};",
            f"            hash = {nix_string(source_hash)};",
            "          };",
            "",
            "          nativeBuildInputs = [",
            "            pkgs.makeWrapper",
            "          ];",
            "",
            "          buildInputs = [",
            "            pkgs.python3",
            "          ];",
            "",
            "          installPhase = ''",
            "            mkdir -p $out/bin $out/share/zsh/site-functions",
            f"            install -D -m 0755 {source_directory}/bin/{name} $out/bin/{name}",
            f"            wrapProgram $out/bin/{name} \\",
            f"              --prefix PATH : ${{pkgs.lib.makeBinPath [ {deps_expr} ]}}",
            f"            if [ -d {source_directory}/completion ]; then",
            f"              cp -r {source_directory}/completion/* $out/share/zsh/site-functions/ 2>/dev/null || true",
            "            fi",
            "          '';",
            "",
            "          meta = {",
            "            platforms = pkgs.lib.platforms.unix;",
            f"            mainProgram = {nix_string(name)};",
            f"            description = {nix_string(description)};",
            "          };",
            "        };",
            "",
        ])
    else:
        # Bash / POSIX script or general utility (default)
        if not nix_deps and "jq" in manifest.get("dependencies", []):
            nix_deps = ["pkgs.jq"]
        deps_expr = " ".join(nix_deps) if nix_deps else "pkgs.coreutils"

        lines.extend([
            f"        {name} = pkgs.stdenvNoCC.mkDerivation {{",
            f"          pname = {nix_string(name)};",
            f"          version = {nix_string(version)};",
            "",
            "          src = pkgs.fetchurl {",
            f"            url = {nix_string(source_url)};",
            f"            hash = {nix_string(source_hash)};",
            "          };",
            "",
            "          nativeBuildInputs = [",
            "            pkgs.makeWrapper",
            "          ];",
            "",
            "          installPhase = ''",
            "            mkdir -p $out/bin $out/share/zsh/site-functions",
            f"            install -D -m 0755 {source_directory}/bin/{name} $out/bin/{name}",
            f"            wrapProgram $out/bin/{name} \\",
            f"              --prefix PATH : ${{pkgs.lib.makeBinPath [ {deps_expr} ]}}",
            f"            if [ -d {source_directory}/completion ]; then",
            f"              cp -r {source_directory}/completion/* $out/share/zsh/site-functions/ 2>/dev/null || true",
            "            fi",
            "          '';",
            "",
            "          meta = {",
            "            platforms = pkgs.lib.platforms.unix;",
            f"            mainProgram = {nix_string(name)};",
            f"            description = {nix_string(description)};",
            "          };",
            "        };",
            "",
        ])

    return lines


def main():
    if not PACKAGES_FILE.exists():
        packages = []
    else:
        packages = json.loads(PACKAGES_FILE.read_text(encoding="utf-8"))

    lines = [
        "{",
        "  description = \"sstix-tools utility registry\";",
        "",
        "  inputs.nixpkgs.url = \"github:NixOS/nixpkgs/nixpkgs-unstable\";",
        "",
        "  outputs = { self, nixpkgs }:",
        "    let",
        "      systems = [",
        "        \"aarch64-darwin\"",
        "        \"x86_64-darwin\"",
        "        \"x86_64-linux\"",
        "        \"aarch64-linux\"",
        "      ];",
        "",
        "      forAllSystems = function:",
        "        nixpkgs.lib.genAttrs systems (system:",
        "          function system nixpkgs.legacyPackages.${system}",
        "        );",
        "",
        "    in {",
        "      packages = forAllSystems (system: pkgs: {",
    ]

    for item in packages:
        lines.extend(generate_package_derivation(item))

    lines.extend([
        "      });",
        "    };",
        "}",
        "",
    ])

    flake_content = "\n".join(lines)

    ROOT_FLAKE_FILE.write_text(flake_content, encoding="utf-8")

    PAGES_FLAKE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PAGES_FLAKE_FILE.write_text(flake_content, encoding="utf-8")

    print(f"Wrote {ROOT_FLAKE_FILE}")
    print(f"Wrote {PAGES_FLAKE_FILE}")


if __name__ == "__main__":
    main()