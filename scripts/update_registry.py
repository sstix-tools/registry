#!/usr/bin/env python3

import base64
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ORG = os.environ["TOOLS_ORG"]
TOKEN = os.environ.get("GH_TOKEN", "")

ROOT = pathlib.Path(__file__).resolve().parents[1]

SITE = ROOT / "site"
REGISTRY_DIR = ROOT / "registry"

STATE_FILE = REGISTRY_DIR / "releases.json"
PACKAGES_FILE = REGISTRY_DIR / "packages.json"

APT_CONF_SOURCE = ROOT / "apt-conf" / "distributions"

APT_DIR = SITE / "apt"
RPM_DIR = SITE / "rpm"
NIX_DIR = SITE / "nix"


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def github_request(path):
    """
    Make a GET request to the GitHub API and return decoded JSON.
    """

    url = "https://api.github.com" + path

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "sstix-tools-registry-updater",
    }

    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(
        url,
        headers=headers,
        method="GET",
    )

    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")

        raise RuntimeError(
            f"GitHub API request failed: {error.code} {error.reason}\n"
            f"URL: {url}\n"
            f"Response: {body}"
        ) from error


def list_all_repositories():
    """
    Return all repositories in the configured organization.
    """

    repositories = []
    page = 1

    while True:
        path = (
            f"/orgs/{urllib.parse.quote(ORG, safe='')}/repos"
            f"?per_page=100&page={page}"
            f"&type=all"
        )

        result = github_request(path)

        if not result:
            break

        repositories.extend(result)

        if len(result) < 100:
            break

        page += 1

    return repositories


def list_all_releases(repository):
    """
    Return all releases for one repository.
    """

    releases = []
    page = 1

    while True:
        path = (
            f"/repos/{urllib.parse.quote(ORG, safe='')}/"
            f"{urllib.parse.quote(repository, safe='')}/releases"
            f"?per_page=100&page={page}"
        )

        result = github_request(path)

        if not result:
            break

        releases.extend(result)

        if len(result) < 100:
            break

        page += 1

    return releases


def assets_by_name(release):
    """
    Convert the GitHub release asset list into a dictionary by filename.
    """

    return {
        asset["name"]: asset
        for asset in release.get("assets", [])
    }


def download(url, destination):
    """
    Download a GitHub release asset.
    """

    headers = {
        "Accept": "application/octet-stream",
        "User-Agent": "sstix-tools-registry-updater",
    }

    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(
        url,
        headers=headers,
        method="GET",
    )

    destination = pathlib.Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with urllib.request.urlopen(request) as response:
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output)

    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")

        raise RuntimeError(
            f"Could not download release asset: {error.code} {error.reason}\n"
            f"URL: {url}\n"
            f"Response: {body}"
        ) from error

    if destination.stat().st_size == 0:
        raise RuntimeError(
            f"Downloaded an empty file from {url}"
        )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def calculate_sri_sha256(path):
    """
    Calculate a Nix-compatible SRI SHA-256 hash.
    """

    digest = hashlib.sha256()

    with pathlib.Path(path).open("rb") as input_file:
        while chunk := input_file.read(1024 * 1024):
            digest.update(chunk)

    encoded = base64.b64encode(digest.digest()).decode("ascii")

    return f"sha256-{encoded}"


def verify_sri_hash(path, expected_hash):
    """
    Verify a file against a Nix SRI SHA-256 hash.
    """

    expected_hash = expected_hash.strip()
    actual_hash = calculate_sri_sha256(path)

    if actual_hash != expected_hash:
        raise RuntimeError(
            f"Hash mismatch for {path}\n"
            f"Expected: {expected_hash}\n"
            f"Actual:   {actual_hash}"
        )


def read_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8") as input_file:
        return json.load(input_file)


def write_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Release discovery
# ---------------------------------------------------------------------------

def discover_registry_releases():
    """
    Find all releases that contain manifest.json.

    A release is accepted only if it is:
    - published
    - not a draft
    - not a prerelease
    - equipped with manifest.json
    """

    discovered = []

    repositories = list_all_repositories()

    for repository_data in repositories:
        repository_name = repository_data["name"]

        # Optional: uncomment this if you want to require a repository topic.
        #
        # topics = repository_data.get("topics", [])
        # if "package-source" not in topics:
        #     continue

        releases = list_all_releases(repository_name)

        for release in releases:
            if release.get("draft"):
                continue

            if release.get("prerelease"):
                continue

            assets = assets_by_name(release)

            if "manifest.json" not in assets:
                continue

            discovered.append(
                {
                    "repository": repository_name,
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

    return discovered


# ---------------------------------------------------------------------------
# Package-manager metadata generation
# ---------------------------------------------------------------------------

def generate_apt_metadata(deb_files):
    """
    Build the APT repository with reprepro.

    The source distribution configuration is read from:

        apt-conf/distributions

    and copied into the generated repository at:

        site/apt/conf/distributions
    """

    if not deb_files:
        raise RuntimeError(
            "No Debian packages were found"
        )

    if not APT_CONF_SOURCE.exists():
        raise RuntimeError(
            f"Missing APT distribution configuration: {APT_CONF_SOURCE}"
        )

    conf_directory = APT_DIR / "conf"
    distributions_file = conf_directory / "distributions"

    conf_directory.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(
        APT_CONF_SOURCE,
        distributions_file,
    )

    print(
        f"Using APT configuration: {APT_CONF_SOURCE}"
    )

    print(
        f"Copied APT configuration to: {distributions_file}"
    )

    for deb_file in deb_files:
        print(f"Importing Debian package: {deb_file}")

        subprocess.run(
            [
                "reprepro",
                "--basedir",
                str(APT_DIR),
                "includedeb",
                "stable",
                str(deb_file),
            ],
            check=True,
        )

def generate_rpm_metadata():
    """
    Build RPM repository metadata.
    """

    print(f"Generating RPM metadata in {RPM_DIR}")

    subprocess.run(
        [
            "createrepo_c",
            "--update",
            str(RPM_DIR),
        ],
        check=True,
    )


# ---------------------------------------------------------------------------
# Main registry update
# ---------------------------------------------------------------------------

def main():
    print(f"Discovering releases in organization: {ORG}")

    discovered = discover_registry_releases()

    if not discovered:
        raise RuntimeError(
            "No valid releases containing manifest.json were found"
        )

    print(f"Found {len(discovered)} registry releases")

    # Rebuild the generated site from all published releases.
    #
    # This means old package versions remain available as long as their
    # GitHub Releases still exist.
    if SITE.exists():
        shutil.rmtree(SITE)

    APT_DIR.mkdir(parents=True, exist_ok=True)
    RPM_DIR.mkdir(parents=True, exist_ok=True)
    NIX_DIR.mkdir(parents=True, exist_ok=True)

    imported = []
    apt_packages = []
    package_keys = set()

    with tempfile.TemporaryDirectory(prefix="registry-update-") as directory:
        temporary = pathlib.Path(directory)
        apt_incoming = temporary / "apt-incoming"
        apt_incoming.mkdir(parents=True)

        for release in discovered:
            repository = release["repository"]
            release_id = release["release_id"]
            tag = release["tag"]
            assets = release["assets"]

            print(f"Processing {repository} {tag}")

            manifest_asset = assets["manifest.json"]

            manifest_path = (
                temporary /
                f"{repository}-{release_id}-manifest.json"
            )

            download(
                manifest_asset["browser_download_url"],
                manifest_path,
            )

            manifest = read_json(manifest_path)

            required_manifest_fields = (
                "name",
                "version",
                "source_archive",
                "apt_package",
                "rpm_package",
            )

            for field in required_manifest_fields:
                if field not in manifest:
                    raise RuntimeError(
                        f"{repository} {tag}: manifest.json "
                        f"is missing field '{field}'"
                    )

            package_name = manifest["name"]
            version = manifest["version"]
            source_name = manifest["source_archive"]
            apt_name = manifest["apt_package"]
            rpm_name = manifest["rpm_package"]
            sri_name = f"{source_name}.sri"

            package_key = (package_name, version)

            if package_key in package_keys:
                raise RuntimeError(
                    f"Duplicate package/version found: "
                    f"{package_name} {version}"
                )

            package_keys.add(package_key)

            required_assets = (
                apt_name,
                rpm_name,
                source_name,
                sri_name,
            )

            for asset_name in required_assets:
                if asset_name not in assets:
                    raise RuntimeError(
                        f"{repository} {tag}: release is missing "
                        f"asset '{asset_name}'"
                    )

            # ---------------------------------------------------------------
            # Debian package
            # ---------------------------------------------------------------

            deb_file = apt_incoming / apt_name

            download(
                assets[apt_name]["browser_download_url"],
                deb_file,
            )

            apt_packages.append(deb_file)

            # ---------------------------------------------------------------
            # RPM package
            # ---------------------------------------------------------------

            rpm_file = RPM_DIR / rpm_name

            download(
                assets[rpm_name]["browser_download_url"],
                rpm_file,
            )

            # ---------------------------------------------------------------
            # Nix source archive and hash
            # ---------------------------------------------------------------

            source_file = NIX_DIR / source_name
            source_hash_file = NIX_DIR / sri_name

            download(
                assets[source_name]["browser_download_url"],
                source_file,
            )

            download(
                assets[sri_name]["browser_download_url"],
                source_hash_file,
            )

            source_hash = source_hash_file.read_text(
                encoding="utf-8"
            ).strip()

            verify_sri_hash(
                source_file,
                source_hash,
            )

            source_url = (
                f"https://github.com/{ORG}/"
                f"{repository}/releases/download/"
                f"{urllib.parse.quote(tag, safe='')}/"
                f"{urllib.parse.quote(source_name, safe='')}"
            )

            imported.append(
                {
                    "repository": repository,
                    "release_id": release_id,
                    "tag": tag,
                    "release_url": release["release_url"],
                    "name": package_name,
                    "version": version,
                    "manifest": manifest,
                    "source_archive": source_name,
                    "source_hash": source_hash,
                    "source_url": source_url,
                }
            )

    # Write state after all releases have passed validation.
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

    write_json(STATE_FILE, state)
    write_json(PACKAGES_FILE, imported)

    print(f"Wrote {STATE_FILE}")
    print(f"Wrote {PACKAGES_FILE}")

    # Build the package repositories.
    generate_apt_metadata(apt_packages)
    generate_rpm_metadata()

    # Generate the Nix flake.
    flake_generator = ROOT / "scripts" / "generate_flake.py"

    if not flake_generator.exists():
        raise RuntimeError(
            f"Missing Nix flake generator: {flake_generator}"
        )

    subprocess.run(
        [
            sys.executable,
            str(flake_generator),
        ],
        check=True,
    )

    print("Registry update completed successfully")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)