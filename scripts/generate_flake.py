#!/usr/bin/env python3

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
packages_file = ROOT / "registry" / "packages.json"
flake_file = ROOT / "site" / "nix" / "flake.nix"

packages = json.loads(packages_file.read_text())

lines = [
    "{",
    "  description = \"my-tools utility registry\";",
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
    "      forAllSystems = f:",
    "        nixpkgs.lib.genAttrs systems",
    "          (system: f (import nixpkgs { inherit system; }));",
    "",
    "    in {",
    "      packages = forAllSystems (pkgs: {",
]

for item in packages:
    name = item["name"]
    version = item["version"]
    source_url = item["source_url"]
    source_hash = item["source_hash"]

    lines.extend(
        [
            f"        {name} = pkgs.stdenvNoCC.mkDerivation {{",
            f"          pname = \"{name}\";",
            f"          version = \"{version}\";",
            "",
            "          src = pkgs.fetchurl {",
            f"            url = \"{source_url}\";",
            f"            hash = \"{source_hash}\";",
            "          };",
            "",
            "          nativeBuildInputs = [ pkgs.makeWrapper ];",
            "          buildInputs = [ pkgs.jq ];",
            "",
            "          installPhase = ''",
            "            mkdir -p $out/bin",
            f"            install -m 0755 {name}/bin/{name} $out/bin/{name}",
            "          '';",
            "",
            "          meta = {",
            "            platforms = pkgs.lib.platforms.unix;",
            f"            description = \"{name} from my-tools\";",
            "          };",
            "        };",
            "",
        ]
    )

lines.extend(
    [
        "      });",
        "",
        "      packages = forAllSystems (pkgs: {",
        "        default = pkgs.lib.attrValues self.packages.${pkgs.system};",
        "      });",
        "    };",
        "}",
        "",
    ]
)

flake_file.parent.mkdir(parents=True, exist_ok=True)
flake_file.write_text("\n".join(lines))