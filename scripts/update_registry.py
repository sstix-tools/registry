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

ORG = os.environ.get("TOOLS_ORG", "sstix-tools")
TOKEN = os.environ.get("GH_TOKEN", "")
GPG_PRIVATE_KEY = os.environ.get("GPG_PRIVATE_KEY", "")

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

        try:
            result = github_request(path)
        except RuntimeError as e:
            print(f"Warning: Could not list org repositories: {e}")
            break

        if not result or not isinstance(result, list):
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

        try:
            result = github_request(path)
        except RuntimeError as e:
            print(f"Warning: Could not list releases for {repository}: {e}")
            break

        if not result or not isinstance(result, list):
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
# GPG Setup & Key Management
# ---------------------------------------------------------------------------

def setup_gpg():
    """
    Check if GPG is available and import private key if GPG_PRIVATE_KEY is set.
    If no key exists, automatically generates a repository signing key.
    Returns primary signing key ID or None.
    """

    if not shutil.which("gpg"):
        print("GPG CLI not available; skipping repository signing")
        return None

    if GPG_PRIVATE_KEY:
        print("Importing GPG private key from GPG_PRIVATE_KEY environment variable")
        import_proc = subprocess.run(
            ["gpg", "--batch", "--yes", "--import"],
            input=GPG_PRIVATE_KEY.encode("utf-8"),
            capture_output=True,
        )
        if import_proc.returncode != 0:
            print(f"Warning: Failed to import GPG key: {import_proc.stderr.decode('utf-8')}")

    # Check for secret keys in keyring
    key_proc = subprocess.run(
        ["gpg", "--batch", "--with-colons", "--list-secret-keys"],
        capture_output=True,
        text=True,
    )

    key_id = None
    if key_proc.returncode == 0 and key_proc.stdout:
        for line in key_proc.stdout.splitlines():
            parts = line.split(":")
            if parts[0] == "sec" and len(parts) > 4 and parts[4]:
                key_id = parts[4]
                break
            elif parts[0] == "fpr" and len(parts) > 9 and parts[9]:
                key_id = parts[9]
                break

    if not key_id:
        print("No secret GPG keys found; generating standard repository key...")
        gen_proc = subprocess.run(
            [
                "gpg",
                "--batch",
                "--passphrase",
                "",
                "--quick-generate-key",
                f"{ORG} Package Signing Key <packages@{ORG}.local>",
                "default",
                "default",
                "never",
            ],
            capture_output=True,
            text=True,
        )
        if gen_proc.returncode == 0:
            key_proc = subprocess.run(
                ["gpg", "--batch", "--with-colons", "--list-secret-keys"],
                capture_output=True,
                text=True,
            )
            for line in key_proc.stdout.splitlines():
                parts = line.split(":")
                if parts[0] == "sec" and len(parts) > 4 and parts[4]:
                    key_id = parts[4]
                    break
                elif parts[0] == "fpr" and len(parts) > 9 and parts[9]:
                    key_id = parts[9]
                    break

    if key_id:
        print(f"Found GPG signing key: {key_id}")
        export_public_keys(key_id)
        return key_id

    return None


def export_public_keys(key_id):
    """
    Export public GPG key into site/ directory for client verification.
    """

    SITE.mkdir(parents=True, exist_ok=True)
    APT_DIR.mkdir(parents=True, exist_ok=True)
    RPM_DIR.mkdir(parents=True, exist_ok=True)

    # Binary GPG Keyring
    gpg_bin_path = SITE / "sstix-tools.gpg"
    subprocess.run(
        ["gpg", "--batch", "--yes", "--export", key_id],
        stdout=gpg_bin_path.open("wb"),
        check=True,
    )
    # Copy for APT keyring convention
    shutil.copyfile(gpg_bin_path, APT_DIR / "sstix-tools.gpg")

    # Armored GPG Public Key
    asc_path = SITE / "sstix-tools.asc"
    subprocess.run(
        ["gpg", "--batch", "--yes", "--armor", "--export", key_id],
        stdout=asc_path.open("wb"),
        check=True,
    )
    # Copy for RPM key convention
    shutil.copyfile(asc_path, RPM_DIR / "RPM-GPG-KEY-sstix-tools")

    print(f"Exported public GPG keys to {gpg_bin_path} and {asc_path}")


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
                    "release_url": release.get("html_url", release.get("url", "")),
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

def generate_apt_metadata(deb_files, signing_key_id=None):
    """
    Build the APT repository with reprepro.
    """

    if not deb_files:
        print("No Debian packages to index")
        return

    if not shutil.which("reprepro"):
        print("Warning: reprepro not found; skipping APT metadata generation")
        return

    conf_directory = APT_DIR / "conf"
    distributions_file = conf_directory / "distributions"
    conf_directory.mkdir(parents=True, exist_ok=True)

    dist_content = APT_CONF_SOURCE.read_text(encoding="utf-8") if APT_CONF_SOURCE.exists() else (
        "Origin: sstix-tools\n"
        "Label: sstix-tools\n"
        "Suite: stable\n"
        "Codename: stable\n"
        "Architectures: amd64 arm64 all\n"
        "Components: main\n"
        "Description: sstix-tools Debian repository\n"
    )

    if signing_key_id:
        dist_content = dist_content.strip() + f"\nSignWith: {signing_key_id}\n"

    distributions_file.write_text(dist_content, encoding="utf-8")

    for deb_file in deb_files:
        print(f"Importing Debian package: {deb_file}")

        subprocess.run(
            [
                "reprepro",
                "--basedir",
                str(APT_DIR),
                "--export=silent-never",
                "--ignore=surprisingbinary",
                "includedeb",
                "stable",
                str(deb_file),
            ],
            check=True,
        )

    # Ensure repository export
    subprocess.run(
        [
            "reprepro",
            "--basedir",
            str(APT_DIR),
            "export",
            "stable",
        ],
        check=True,
    )


def generate_rpm_metadata(signing_key_id=None):
    """
    Build RPM repository metadata with createrepo_c.
    """

    if not shutil.which("createrepo_c"):
        print("Warning: createrepo_c not found; skipping RPM metadata generation")
        return

    print(f"Generating RPM metadata in {RPM_DIR}")

    subprocess.run(
        [
            "createrepo_c",
            "--update",
            str(RPM_DIR),
        ],
        check=True,
    )

    # Sign repomd.xml if GPG signing key is available
    repomd_file = RPM_DIR / "repodata" / "repomd.xml"
    if signing_key_id and repomd_file.exists() and shutil.which("gpg"):
        print(f"Signing RPM repodata with key {signing_key_id}")
        asc_file = RPM_DIR / "repodata" / "repomd.xml.asc"
        if asc_file.exists():
            asc_file.unlink()
        subprocess.run(
            [
                "gpg",
                "--batch",
                "--yes",
                "--detach-sign",
                "--armor",
                "-u",
                signing_key_id,
                str(repomd_file),
            ],
            check=True,
        )


# ---------------------------------------------------------------------------
# Main registry update
# ---------------------------------------------------------------------------

def main():
    print(f"Discovering releases in organization: {ORG}")

    signing_key_id = setup_gpg()

    discovered = discover_registry_releases()

    print(f"Found {len(discovered)} registry releases")

    # If no releases found, load existing packages.json or empty
    if not discovered:
        print("No valid releases containing manifest.json were found in organization.")
        if not PACKAGES_FILE.exists():
            write_json(PACKAGES_FILE, [])
        if not STATE_FILE.exists():
            write_json(STATE_FILE, [])
        return

    # Rebuild the generated site from all published releases.
    if SITE.exists():
        shutil.rmtree(SITE)

    APT_DIR.mkdir(parents=True, exist_ok=True)
    RPM_DIR.mkdir(parents=True, exist_ok=True)
    NIX_DIR.mkdir(parents=True, exist_ok=True)

    if signing_key_id:
        export_public_keys(signing_key_id)

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

            package_name = manifest.get("name", repository)
            version = manifest.get("version", tag.lstrip("v"))
            source_name = manifest.get("source_archive", f"{package_name}-{version}.tar.gz")

            package_key = (package_name, version)
            if package_key in package_keys:
                print(f"Warning: Skipping duplicate package/version {package_name} {version}")
                continue

            package_keys.add(package_key)

            # Collect APT packages (support string or list)
            deb_names = manifest.get("apt_packages") or (
                [manifest["apt_package"]] if "apt_package" in manifest else []
            )

            # Collect RPM packages (support string or list)
            rpm_names = manifest.get("rpm_packages") or (
                [manifest["rpm_package"]] if "rpm_package" in manifest else []
            )

            # Download Debian packages
            for deb_name in deb_names:
                if deb_name in assets:
                    deb_file = apt_incoming / deb_name
                    download(assets[deb_name]["browser_download_url"], deb_file)
                    apt_packages.append(deb_file)
                else:
                    print(f"Warning: {repository} {tag} missing APT asset '{deb_name}'")

            # Download RPM packages
            for rpm_name in rpm_names:
                if rpm_name in assets:
                    rpm_file = RPM_DIR / rpm_name
                    download(assets[rpm_name]["browser_download_url"], rpm_file)
                else:
                    print(f"Warning: {repository} {tag} missing RPM asset '{rpm_name}'")

            # Handle Nix source archive and hash
            source_file = NIX_DIR / source_name
            sri_name = f"{source_name}.sri"

            if source_name in assets:
                download(assets[source_name]["browser_download_url"], source_file)
                
                # Check for explicit SRI hash asset or in manifest
                if sri_name in assets:
                    source_hash_file = NIX_DIR / sri_name
                    download(assets[sri_name]["browser_download_url"], source_hash_file)
                    source_hash = source_hash_file.read_text(encoding="utf-8").strip()
                elif "source_hash" in manifest:
                    source_hash = manifest["source_hash"]
                else:
                    source_hash = calculate_sri_sha256(source_file)

                verify_sri_hash(source_file, source_hash)

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
    generate_apt_metadata(apt_packages, signing_key_id=signing_key_id)
    generate_rpm_metadata(signing_key_id=signing_key_id)

    # Generate the Nix flake.
    flake_generator = ROOT / "scripts" / "generate_flake.py"
    if flake_generator.exists():
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