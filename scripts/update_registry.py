#!/usr/bin/env python3

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

ORG = os.environ["TOOLS_ORG"]
TOKEN = os.environ.get("GH_TOKEN", "")

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
APT_POOL = SITE / "apt" / "pool" / "main"
RPM_DIR = SITE / "rpm"
NIX_DIR = SITE / "nix"
STATE_FILE = ROOT / "registry" / "releases.json"


def github_request(path):
    url = "https://api.github.com" + path

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {TOKEN}",
            "User-Agent": "sstix-tools-registry-updater",
        },
    )

    with urllib.request.urlopen(request) as response:
        return json.load(response)


def download(url, destination):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "Authorization": f"Bearer {TOKEN}",
            "User-Agent": "sstix-tools-registry-updater",
        },
    )

    with urllib.request.urlopen(request) as response:
        with open(destination, "wb") as output:
            shutil.copyfileobj(response, output)


def list_all_repositories():
    repositories = []
    page = 1

    while True:
        result = github_request(
            f"/orgs/{urllib.parse.quote(ORG)}/repos"
            f"?per_page=100&page={page}"
        )

        if not result:
            break

        repositories.extend(result)
        page += 1

    return repositories


def list_all_releases(repository):
    releases = []
    page = 1

    while True:
        result = github_request(
            f"/repos/{ORG}/{repository}/releases"
            f"?per_page=100&page={page}"
        )

        if not result:
            break

        releases.extend(result)
        page += 1

    return releases


def release_assets(release):
    return {
        asset["name"]: asset
        for asset in release.get("assets", [])
    }


def main():
    old_state = []

    if STATE_FILE.exists():
        old_state = json.loads(STATE_FILE.read_text())

    old_keys = {
        (item["repository"], item["release_id"])
        for item in old_state
    }

    discovered = []

    for repository in list_all_repositories():
        repo_name = repository["name"]

        for release in list_all_releases(repo_name):
            if release.get("draft"):
                continue

            if release.get("prerelease"):
                continue

            assets = release_assets(release)

            if "manifest.json" not in assets:
                continue

            discovered.append(
                {
                    "repository": repo_name,
                    "release_id": release["id"],
                    "tag": release["tag_name"],
                    "release_url": release["html_url"],
                    "assets": assets,
                }
            )

    discovered.sort(
        key=lambda item: (
            item["repository"],
            item["tag"],
        )
    )

    with tempfile.TemporaryDirectory() as temporary:
        temporary = pathlib.Path(temporary)

        if SITE.exists():
            shutil.rmtree(SITE)

        APT_POOL.mkdir(parents=True)
        RPM_DIR.mkdir(parents=True)
        NIX_DIR.mkdir(parents=True)

        imported = []

        for release in discovered:
            repository = release["repository"]
            release_id = release["release_id"]
            assets = release["assets"]

            manifest_asset = assets["manifest.json"]
            manifest_path = temporary / f"{repository}-{release_id}-manifest.json"

            download(manifest_asset["browser_download_url"], manifest_path)
            manifest = json.loads(manifest_path.read_text())

            package_name = manifest["name"]
            version = manifest["version"]

            prefix = f"{repository}-{release_id}"

            for field in ("apt_package", "rpm_package", "source_archive"):
                asset_name = manifest[field]

                if asset_name not in assets:
                    raise RuntimeError(
                        f"{repository} {release['tag']} is missing {asset_name}"
                    )

            apt_name = manifest["apt_package"]
            rpm_name = manifest["rpm_package"]
            source_name = manifest["source_archive"]

            apt_destination = APT_POOL / package_name / apt_name
            rpm_destination = RPM_DIR / rpm_name
            source_destination = NIX_DIR / source_name
            hash_destination = NIX_DIR / f"{source_name}.sri"

            apt_destination.parent.mkdir(parents=True, exist_ok=True)

            download(
                assets[apt_name]["browser_download_url"],
                apt_destination,
            )

            download(
                assets[rpm_name]["browser_download_url"],
                rpm_destination,
            )

            download(
                assets[source_name]["browser_download_url"],
                source_destination,
            )

            hash_name = f"{source_name}.sri"

            if hash_name in assets:
                download(
                    assets[hash_name]["browser_download_url"],
                    hash_destination,
                )
                source_hash = hash_destination.read_text().strip()
            else:
                raise RuntimeError(
                    f"{repository} {release['tag']} is missing {hash_name}"
                )

            imported.append(
                {
                    "repository": repository,
                    "release_id": release_id,
                    "tag": release["tag"],
                    "name": package_name,
                    "version": version,
                    "release_url": release["release_url"],
                    "manifest": manifest,
                    "source_archive": source_name,
                    "source_hash": source_hash,
                    "source_url": (
                        f"https://github.com/{ORG}/{repository}"
                        f"/releases/download/{release['tag']}/{source_name}"
                    ),
                }
            )

        state = [
            {
                "repository": item["repository"],
                "release_id": item["release_id"],
                "tag": item["tag"],
                "name": item["name"],
                "version": item["version"],
            }
            for item in imported
        ]

        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n"
        )

        manifest_path = ROOT / "registry" / "packages.json"
        manifest_path.write_text(
            json.dumps(imported, indent=2, sort_keys=True) + "\n"
        )

        generate_apt_metadata()
        generate_rpm_metadata()

        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "generate_flake.py"),
            ],
            check=True,
        )


def generate_apt_metadata():
    apt_directory = SITE / "apt"

    distribution = apt_directory / "conf" / "distributions"
    distribution.parent.mkdir(parents=True, exist_ok=True)

    distribution.write_text(
        """Origin: sstix-tools
Label: sstix-tools
Suite: stable
Codename: stable
Architectures: amd64 arm64 all
Components: main
Description: sstix-tools Debian repository
"""
    )

    subprocess.run(
        [
            "reprepro",
            "--basedir",
            str(apt_directory),
            "includedeb",
            "stable",
        ],
        input=b"",
        check=False,
    )

    # The actual .deb files are already in pool/. Generate indexes with
    # apt-ftparchive as a simple static repository fallback.
    subprocess.run(
        [
            "apt-ftparchive",
            "packages",
            str(apt_directory / "pool"),
        ],
        stdout=open(apt_directory / "Packages", "w"),
        check=True,
    )

    subprocess.run(
        ["gzip", "-9", "-f", str(apt_directory / "Packages")],
        check=True,
    )


def generate_rpm_metadata():
    subprocess.run(
        ["createrepo_c", str(SITE / "rpm")],
        check=True,
    )


if __name__ == "__main__":
    main()