# sstix-tools Package Registry

Central package registry and distribution hub for `sstix-tools` command-line utilities.

This registry automatically indexes and hosts releases for Debian/Ubuntu (APT), Fedora/RHEL/CentOS (RPM), and Nix across supported platforms (`x86_64-linux`, `aarch64-linux`, `x86_64-darwin`, `aarch64-darwin`).

- **Registry Web / Repository Base**: [https://sstix-tools.github.io/registry/](https://sstix-tools.github.io/registry/)
- **APT Repository**: `https://sstix-tools.github.io/registry/apt/`
- **RPM Repository**: `https://sstix-tools.github.io/registry/rpm/`
- **Nix Flake**: `github:sstix-tools/registry`

---

## Adding the Repositories & Installing Packages

### 1. APT (Debian / Ubuntu / Linux Mint / Pop!_OS)

1. Add the repository to your APT sources:

```bash
echo "deb [trusted=yes] https://sstix-tools.github.io/registry/apt stable main" | sudo tee /etc/apt/sources.list.d/sstix-tools.list
```

2. Update package lists and install any tool:

```bash
sudo apt update
sudo apt install <package-name>
```

**Example:**
```bash
sudo apt update
sudo apt install example-tool
```

---

### 2. RPM (Fedora / RHEL / CentOS / Rocky Linux / AlmaLinux)

1. Create a repository file at `/etc/yum.repos.d/sstix-tools.repo`:

```bash
sudo tee /etc/yum.repos.d/sstix-tools.repo << 'EOF'
[sstix-tools]
name=sstix-tools Repository
baseurl=https://sstix-tools.github.io/registry/rpm
enabled=1
gpgcheck=0
EOF
```

2. Install any package using `dnf` or `yum`:

```bash
sudo dnf install <package-name>
```

**Example:**
```bash
sudo dnf install example-tool
```

*(For openSUSE / Zypper)*:
```bash
sudo zypper addrepo https://sstix-tools.github.io/registry/rpm sstix-tools
sudo zypper refresh
sudo zypper install example-tool
```

---

### 3. Nix (NixOS / Linux / macOS)

The registry exposes a Nix Flake containing all published utilities.

#### Run Directly (Ephemeral)
Run any utility without permanently installing it:

```bash
nix run github:sstix-tools/registry#<package-name>
```

**Example:**
```bash
nix run github:sstix-tools/registry#example-tool
```

#### Run in a Temporary Shell
Drop into a shell environment with the tool available in your `$PATH`:

```bash
nix shell github:sstix-tools/registry#<package-name>
```

#### Install into User Profile
Install the utility globally into your active Nix profile:

```bash
nix profile install github:sstix-tools/registry#<package-name>
```

#### Use in `flake.nix` or NixOS / Home Manager Configuration
Add the registry as an input in your `flake.nix`:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    sstix-tools.url = "github:sstix-tools/registry";
  };

  outputs = { self, nixpkgs, sstix-tools }:
    let
      system = "x86_64-linux"; # or "aarch64-darwin", "x86_64-darwin", "aarch64-linux"
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      # In NixOS configuration / Home Manager:
      # environment.systemPackages = [ sstix-tools.packages.${system}.example-tool ];
      # or
      # home.packages = [ sstix-tools.packages.${system}.example-tool ];
    };
}
```

---

## How It Works

1. **Ingestion (`scripts/update_registry.py`)**: Runs periodically via GitHub Actions (`update.yml`), scanning all repositories in the `sstix-tools` organization for tagged releases containing a `manifest.json`.
2. **Metadata Generation**:
   - APT repository metadata generated via `reprepro`.
   - RPM repository metadata generated via `createrepo_c`.
   - Nix Flake generated via `scripts/generate_flake.py`.
3. **Deployment (`pages.yml`)**: Deploys the APT repository, RPM repository, and Nix flake to GitHub Pages.
