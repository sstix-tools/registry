#!/usr/bin/env python3

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

PACKAGES_FILE = ROOT / "registry" / "packages.json"

# This is the file that `github:sstix-tools/registry` expects.
ROOT_FLAKE_FILE = ROOT / "flake.nix"

# Optional copy for the GitHub Pages output.
PAGES_FLAKE_FILE = ROOT / "site" / "nix" / "flake.nix"


packages = json.loads(
    PACKAGES_FILE.read_text(encoding="utf-8")
)


def nix_string(value):
    """
    Encode a Python string as a valid Nix string literal.
    """
    return json.dumps(value)


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
    "          function system",
    "        );",
    "",
    "    in {",
    "      packages = forAllSystems (system: pkgs: {",
]

for item in packages:
    name = item["name"]
    version = item["version"]
    source_url = item["source_url"]
    source_hash = item["source_hash"]

    source_directory = f"{name}-{version}"

    lines.extend(
        [
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
            "            mkdir -p $out/bin",
            "",
            f"            install -m 0755 {source_directory}/bin/{name} \\",
            f"              $out/bin/{name}",
            "",
            f"            wrapProgram $out/bin/{name} \\",
            "              --prefix PATH : "
            "${pkgs.lib.makeBinPath [ pkgs.jq ]}",
            "          '';",
            "",
            "          meta = {",
            "            platforms = pkgs.lib.platforms.unix;",
            f"            mainProgram = {nix_string(name)};",
            f"            description = {nix_string(name + ' from sstix-tools')};",
            "          };",
            "        };",
            "",
        ]
    )

lines.extend(
    [
        "      });",
        "    };",
        "}",
        "",
    ]
)

flake_content = "\n".join(lines)

ROOT_FLAKE_FILE.write_text(
    flake_content,
    encoding="utf-8",
)

PAGES_FLAKE_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)

PAGES_FLAKE_FILE.write_text(
    flake_content,
    encoding="utf-8",
)

print(f"Wrote {ROOT_FLAKE_FILE}")
print(f"Wrote {PAGES_FLAKE_FILE}")