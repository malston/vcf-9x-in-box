# VCF Secrets Management

This document explains how to securely manage passwords and sensitive information for your VCF deployment.

## Security Problem

By default, `config/vcf-config.yaml` contains all configuration including passwords in plain text. This is:
- ❌ **Insecure** - passwords visible in git repository
- ❌ **Dangerous** - accidental commits expose credentials
- ❌ **Non-compliant** - violates security best practices

## Secure Solutions

We provide **multiple secure options** with priority order:

### Priority Order

1. **Environment Variables** (most secure)
2. **Secrets File** (`config/vcf-secrets.yaml` - gitignored)
3. **Config File** (`config/vcf-config.yaml` - fallback)
4. **Interactive Prompt** (if not found anywhere)

---

## Option 1: Environment Variables (Recommended)

### Setup

```bash
# Export environment variables (add to ~/.zshrc or ~/.bashrc for persistence)
export VCF_ESXI_ROOT_PASSWORD="VMware1!"
export VCF_INSTALLER_ROOT_PASSWORD="VMware1!VMware1!"
export VCF_INSTALLER_ADMIN_PASSWORD="VMware1!VMware1!"
export VCF_VCENTER_PASSWORD="VMware1!VMware1!"
```

### Usage

```bash
# Variables are automatically used by scripts
make deploy-vcf-installer
make setup-ssh-keys
```

### Benefits

✓ Most secure - never written to disk
✓ Can use OS keychain/secrets manager
✓ Easy CI/CD integration
✓ No accidental git commits

---

## Option 2: Secrets File (Good for Local Development)

### Setup

1. **Copy the example file:**

```bash
cp config/vcf-secrets.yaml.example config/vcf-secrets.yaml
```

2. **Edit with your passwords:**

```bash
vim config/vcf-secrets.yaml
```

```yaml
# ESXi root password (used by all ESXi hosts)
esxi_root_password: "YourSecurePasswordHere"

# VCF Installer passwords (must be 12+ characters)
vcf_installer_root_password: "YourVCFInstallerRootPassword"
vcf_installer_admin_password: "YourVCFInstallerAdminPassword"

# vCenter password (must be 12+ characters)
vcenter_password: "YourVCenterPassword"
```

3. **File is automatically gitignored:**

```bash
# Verify it's ignored
git status
# vcf-secrets.yaml should NOT appear
```

### Usage

```bash
# Scripts automatically load from secrets file
make deploy-vcf-installer
make setup-ssh-keys
```

### Benefits

✓ Secure - gitignored by default
✓ Easy to use locally
✓ No environment variable management
✓ File permissions protect secrets

---

## Option 3: Config File (Not Recommended)

You can still use passwords in `config/vcf-config.yaml`, but this is **NOT recommended** for security reasons.

### Remove Passwords from Config

Update your `config/vcf-config.yaml` to use placeholders:

```yaml
common:
  root_password: "PLACEHOLDER"  # Will be loaded from secrets

vcf_installer:
  root_password: "PLACEHOLDER"
  admin_password: "PLACEHOLDER"

vcenter:
  password: "PLACEHOLDER"
```

---

## Environment Variable Names

| Password | Environment Variable |
|----------|---------------------|
| ESXi Root Password | `VCF_ESXI_ROOT_PASSWORD` |
| VCF Installer Root | `VCF_INSTALLER_ROOT_PASSWORD` |
| VCF Installer Admin | `VCF_INSTALLER_ADMIN_PASSWORD` |
| vCenter Password | `VCF_VCENTER_PASSWORD` |

---

## Using Secrets in Scripts

### For New Scripts

```python
from vcf_secrets import load_config_with_secrets

# Load config with secrets merged
config = load_config_with_secrets(config_file)

# Passwords are automatically loaded from secure sources
esxi_password = config['common']['root_password']
```

### Secrets Manager API

```python
from vcf_secrets import SecretsManager

secrets_mgr = SecretsManager(project_dir)

# Get password with priority order (env → secrets file → config → prompt)
password = secrets_mgr.get_esxi_root_password(
    config_value=config['common'].get('root_password')
)

# Check secrets status
print(secrets_mgr.get_secrets_info())
```

---

## macOS Keychain Integration (Advanced)

You can store passwords in macOS Keychain and retrieve them via environment variables:

```bash
# Store password in keychain
security add-generic-password -a "$USER" -s "VCF_ESXI_ROOT_PASSWORD" -w "VMware1!"

# Retrieve and export (add to ~/.zshrc)
export VCF_ESXI_ROOT_PASSWORD=$(security find-generic-password -a "$USER" -s "VCF_ESXI_ROOT_PASSWORD" -w)
```

---

## CI/CD Integration

### GitHub Actions

```yaml
env:
  VCF_ESXI_ROOT_PASSWORD: ${{ secrets.VCF_ESXI_ROOT_PASSWORD }}
  VCF_INSTALLER_ROOT_PASSWORD: ${{ secrets.VCF_INSTALLER_ROOT_PASSWORD }}
  VCF_INSTALLER_ADMIN_PASSWORD: ${{ secrets.VCF_INSTALLER_ADMIN_PASSWORD }}
  VCF_VCENTER_PASSWORD: ${{ secrets.VCF_VCENTER_PASSWORD }}
```

### GitLab CI

```yaml
variables:
  VCF_ESXI_ROOT_PASSWORD: ${VCF_ESXI_ROOT_PASSWORD}
  VCF_INSTALLER_ROOT_PASSWORD: ${VCF_INSTALLER_ROOT_PASSWORD}
```

---

## Best Practices

### ✓ DO

- ✓ Use environment variables for production
- ✓ Use secrets file for local development
- ✓ Keep `.example` files in git
- ✓ Use strong passwords (12+ characters)
- ✓ Rotate passwords regularly
- ✓ Use different passwords per environment

### ✗ DON'T

- ✗ Commit `vcf-secrets.yaml` to git
- ✗ Share secrets via email/Slack
- ✗ Use weak passwords
- ✗ Reuse passwords across environments
- ✗ Store secrets in plaintext config files

---

## Troubleshooting

### Check Secrets Status

```bash
python3 -c "
from pathlib import Path
from scripts.vcf_secrets import SecretsManager
mgr = SecretsManager(Path.cwd())
print(mgr.get_secrets_info())
"
```

### Output Example

```
Secrets Priority Order:
  1. Environment variables (VCF_*)
  2. Secrets file (config/vcf-secrets.yaml)
  3. Config file (config/vcf-config.yaml)
  4. Interactive prompt

✓ Secrets file found: /path/to/config/vcf-secrets.yaml

Environment variables:
  ✓ VCF_ESXI_ROOT_PASSWORD is set
    VCF_INSTALLER_ROOT_PASSWORD not set
    VCF_INSTALLER_ADMIN_PASSWORD not set
    VCF_VCENTER_PASSWORD not set
```

### Common Issues

**Issue:** Scripts still asking for passwords

```bash
# Solution: Check if secrets are loaded
python3 -c "
from pathlib import Path
from scripts.vcf_secrets import SecretsManager
mgr = SecretsManager(Path.cwd())
print('Has secrets file:', mgr.has_secrets_file())
"
```

**Issue:** Wrong password being used

```bash
# Solution: Check priority order
# Environment variable overrides secrets file
# Remove env var if you want to use secrets file
unset VCF_ESXI_ROOT_PASSWORD
```

---

## Migration Guide

### Migrating from Plaintext Config

1. **Create secrets file:**
   ```bash
   cp config/vcf-secrets.yaml.example config/vcf-secrets.yaml
   ```

2. **Copy passwords from config:**
   ```bash
   vim config/vcf-secrets.yaml
   # Copy passwords from vcf-config.yaml
   ```

3. **Replace passwords in config with placeholders:**
   ```yaml
   common:
     root_password: "PLACEHOLDER"
   ```

4. **Test:**
   ```bash
   make deploy-vcf-installer-dry-run
   ```

5. **Verify secrets file is gitignored:**
   ```bash
   git status
   # vcf-secrets.yaml should NOT appear
   ```

---

## Security Checklist

- [ ] Removed passwords from `config/vcf-config.yaml`
- [ ] Created `config/vcf-secrets.yaml` with actual passwords
- [ ] Verified `vcf-secrets.yaml` is gitignored (`git status`)
- [ ] Set file permissions: `chmod 600 config/vcf-secrets.yaml`
- [ ] Added `.example` file to git
- [ ] Tested scripts with new secrets approach
- [ ] Documented password requirements for team
- [ ] Set up password rotation schedule

---

**Last Updated:** November 11, 2025
