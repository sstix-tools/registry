# sstix-tools Package Registry

Central package registry and distribution hub for `sstix-tools` command-line utilities, script packages, and Zsh function extensions.

This registry automatically indexes and hosts releases for:
- **Debian / Ubuntu** (APT repository)
- **Fedora / RHEL / CentOS / openSUSE** (RPM repository)
- **Nix / NixOS / Home Manager** (Nix Flake)

Supported architectures: `x86_64-linux`, `aarch64-linux`, `x86_64-darwin`, `aarch64-darwin` (plus `all`/`noarch` for scripts and Zsh functions).

- **Registry Web Base**: [https://sstix-tools.github.io/registry/](https://sstix-tools.github.io/registry/)
- **APT Repository**: `https://sstix-tools.github.io/registry/apt/`
- **RPM Repository**: `https://sstix-tools.github.io/registry/rpm/`
- **Nix Flake**: `github:sstix-tools/registry`
- **GPG Key (Binary)**: `https://sstix-tools.github.io/registry/sstix-tools.gpg`
- **GPG Key (ASCII Armored)**: `https://sstix-tools.github.io/registry/sstix-tools.asc`

---

## 1. Zsh Setup (Completions & Autoloadable Functions)

All packages in `sstix-tools` install completions and functions to standard locations. Ensure your `~/.zshrc` is configured with user paths in `fpath`:

```zsh
# User-installed executables
export PATH="$HOME/.local/bin:$PATH"

# User-installed zsh functions and completions
fpath=(
    "$HOME/.local/share/zsh/functions"
    "$HOME/.local/share/zsh/site-functions"
    $fpath
)

autoload -Uz compinit
compinit
```

### Autoloading Zsh Functions
When you install a Zsh function extension package (e.g. `my-func`), you can autoload it in your shell or `~/.zshrc`:

```zsh
# Autoload a specific function
autoload -Uz my-func

# Or autoload all user-installed functions in fpath
for f in "$HOME/.local/share/zsh/functions"/*(N:t) /usr/share/zsh/functions/*(N:t); do
    autoload -Uz "$f"
done
```

---

## 2. Package Installation

### A. APT (Debian / Ubuntu / Pop!_OS / Linux Mint)

#### Secure Setup (GPG Verified):
```bash
# 1. Download repository GPG signing key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://sstix-tools.github.io/registry/sstix-tools.gpg | sudo tee /etc/apt/keyrings/sstix-tools.gpg > /dev/null

# 2. Add APT repository source list
echo "deb [signed-by=/etc/apt/keyrings/sstix-tools.gpg] https://sstix-tools.github.io/registry/apt stable main" | sudo tee /etc/apt/sources.list.d/sstix-tools.list

# 3. Update & install
sudo apt update
sudo apt install <package-name>
```

*(Unsigned fallback)*:
```bash
echo "deb [trusted=yes] https://sstix-tools.github.io/registry/apt stable main" | sudo tee /etc/apt/sources.list.d/sstix-tools.list
sudo apt update
sudo apt install <package-name>
```

---

### B. RPM (Fedora / RHEL / CentOS / Rocky Linux / AlmaLinux)

#### Secure Setup (GPG Verified):
```bash
sudo tee /etc/yum.repos.d/sstix-tools.repo << 'EOF'
[sstix-tools]
name=sstix-tools Repository
baseurl=https://sstix-tools.github.io/registry/rpm
enabled=1
gpgcheck=1
gpgkey=https://sstix-tools.github.io/registry/sstix-tools.asc
EOF

sudo dnf install <package-name>
```

*(openSUSE / Zypper)*:
```bash
sudo zypper addrepo https://sstix-tools.github.io/registry/rpm sstix-tools
sudo rpm --import https://sstix-tools.github.io/registry/sstix-tools.asc
sudo zypper refresh
sudo zypper install <package-name>
```

---

### C. Nix (Linux / macOS / NixOS)

Tools that provide a `flake.nix` can be run or installed directly from their repository or via the registry aggregator:

#### Run Directly (Ephemeral)
```bash
# Direct from tool repository
nix run github:sstix-tools/<package-name>

# Or via registry aggregator
nix run github:sstix-tools/registry#<package-name>
```

#### Install into Profile
```bash
# Direct from tool repository
nix profile install github:sstix-tools/<package-name>

# Or via registry aggregator
nix profile install github:sstix-tools/registry#<package-name>
```

#### Flake Configuration (`flake.nix` / Home Manager / NixOS)
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
      # In Home Manager:
      # home.packages = [ sstix-tools.packages.${system}.<package-name> ];

      # In NixOS:
      # environment.systemPackages = [ sstix-tools.packages.${system}.<package-name> ];
    };
}
```

---

## 3. Creating & Publishing New Tools

Use one of the official template repositories in `sstix-tools`:

| Template | Description |
|---|---|
| [`template-bash-utility`](https://github.com/sstix-tools/template-bash-utility) | POSIX / Bash script utilities with Zsh completions |
| [`template-python-utility`](https://github.com/sstix-tools/template-python-utility) | Python CLI scripts with dependency wrapping & completions |
| [`template-c-utility`](https://github.com/sstix-tools/template-c-utility) | Compiled C utilities with Makefile & multi-arch binary releases |
| [`template-zsh-function`](https://github.com/sstix-tools/template-zsh-function) | Autoloadable Zsh functions with completions |

### Publishing Workflow
1. Create a repository under the `sstix-tools` organization using the appropriate template.
2. Push your changes and tag a release (e.g. `git tag v1.0.0 && git push origin v1.0.0`).
3. The repository's `release.yaml` workflow builds `.deb`, `.rpm`, source `.tar.gz`, and `manifest.json`.
4. The workflow triggers a `repository_dispatch` to `sstix-tools/registry`, which immediately re-indexes packages and updates GitHub Pages.

---

## 4. Organization Setup & Secrets

To enable instant event-driven registry updates and GPG package signing across the organization:

1. **GitHub Pages**:
   - Go to `registry` repository -> **Settings** -> **Pages** -> Source: **GitHub Actions**.

2. **Registry Dispatch Token (Optional for instant dispatch)**:
   - Create a GitHub Personal Access Token (PAT) with `repo` scope or Organization Fine-Grained Token with repository dispatch permissions on `sstix-tools/registry`.
   - Add it as an organization or repository secret named `REGISTRY_DISPATCH_TOKEN` in tool repositories.
   - *Note*: If omitted, release workflows fall back cleanly and the registry's scheduled hourly cron crawler will ingest the release.

3. **GPG Repository Signing Key (Optional)**:
   - Generate a GPG keypair for package signing:
     ```bash
     gpg --batch --gen-key <<EOF
     Key-Type: RSA
     Key-Length: 4096
     Subkey-Type: RSA
     Subkey-Length: 4096
     Name-Real: sstix-tools Package Registry
     Name-Email: tools@sstix.invalid
     Expire-Date: 0
     %no-protection
     %commit
     EOF
     ```
   - Export the private key:
     ```bash
     gpg --armor --export-secret-keys "sstix-tools Package Registry"
     ```
   - In `sstix-tools/registry` -> **Settings** -> **Secrets and variables** -> **Actions**, add a repository secret named `GPG_PRIVATE_KEY` containing the ASCII-armored private key.
