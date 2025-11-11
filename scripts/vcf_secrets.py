#!/usr/bin/env python3
"""
VCF Secrets Management
Purpose: Securely load passwords from environment variables, secrets file, or config file
Author: Auto-generated for VCF 9.x in a Box project
"""

import getpass
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml module not found. Install with: uv sync")
    sys.exit(1)


class SecretsManager:
    """Manage secrets from multiple sources with priority order"""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.secrets_file = project_dir / "config" / "vcf-secrets.yaml"
        self._secrets_cache = None

    def get_secret(
        self,
        key: str,
        config_value: Optional[str] = None,
        env_var: Optional[str] = None,
        required: bool = True
    ) -> Optional[str]:
        """
        Get secret value with priority order:
        1. Environment variable (if env_var specified)
        2. Secrets file (vcf-secrets.yaml)
        3. Config file value (if config_value provided)
        4. Prompt user (if required=True)

        Args:
            key: Secret key name in secrets file
            config_value: Value from main config file (fallback)
            env_var: Environment variable name to check
            required: If True, will prompt if not found

        Returns:
            Secret value or None if not found and not required
        """
        # Priority 1: Environment variable
        if env_var:
            env_value = os.environ.get(env_var)
            if env_value:
                return env_value

        # Priority 2: Secrets file
        secrets = self._load_secrets_file()
        if secrets and key in secrets:
            return secrets[key]

        # Priority 3: Config file value
        if config_value:
            return config_value

        # Priority 4: Prompt user (if required)
        if required:
            prompt = f"Enter {key.replace('_', ' ')}: "
            return getpass.getpass(prompt)

        return None

    def _load_secrets_file(self) -> Optional[Dict[str, Any]]:
        """Load secrets from vcf-secrets.yaml (cached)"""
        if self._secrets_cache is not None:
            return self._secrets_cache

        if not self.secrets_file.exists():
            return None

        try:
            with open(self.secrets_file, 'r', encoding='utf-8') as f:
                self._secrets_cache = yaml.safe_load(f)
            return self._secrets_cache
        except (OSError, yaml.YAMLError) as e:
            print(f"WARNING: Failed to load secrets file: {e}")
            return None

    def get_esxi_root_password(self, config_value: Optional[str] = None) -> str:
        """Get ESXi root password"""
        password = self.get_secret(
            key="esxi_root_password",
            config_value=config_value,
            env_var="VCF_ESXI_ROOT_PASSWORD",
            required=True
        )
        assert password is not None  # required=True guarantees non-None
        return password

    def get_vcf_installer_root_password(self, config_value: Optional[str] = None) -> str:
        """Get VCF Installer root password"""
        password = self.get_secret(
            key="vcf_installer_root_password",
            config_value=config_value,
            env_var="VCF_INSTALLER_ROOT_PASSWORD",
            required=True
        )
        assert password is not None  # required=True guarantees non-None
        return password

    def get_vcf_installer_admin_password(self, config_value: Optional[str] = None) -> str:
        """Get VCF Installer admin password"""
        password = self.get_secret(
            key="vcf_installer_admin_password",
            config_value=config_value,
            env_var="VCF_INSTALLER_ADMIN_PASSWORD",
            required=True
        )
        assert password is not None  # required=True guarantees non-None
        return password

    def get_vcenter_password(self, config_value: Optional[str] = None) -> str:
        """Get vCenter password"""
        password = self.get_secret(
            key="vcenter_password",
            config_value=config_value,
            env_var="VCF_VCENTER_PASSWORD",
            required=True
        )
        assert password is not None  # required=True guarantees non-None
        return password

    def has_secrets_file(self) -> bool:
        """Check if secrets file exists"""
        return self.secrets_file.exists()

    def get_secrets_info(self) -> str:
        """Get information about secrets sources"""
        lines = []
        lines.append("Secrets Priority Order:")
        lines.append("  1. Environment variables (VCF_*)")
        lines.append("  2. Secrets file (config/vcf-secrets.yaml)")
        lines.append("  3. Config file (config/vcf-config.yaml)")
        lines.append("  4. Interactive prompt")
        lines.append("")

        if self.has_secrets_file():
            lines.append(f"✓ Secrets file found: {self.secrets_file}")
        else:
            lines.append(f"⚠ Secrets file not found: {self.secrets_file}")
            lines.append(f"  Create from: {self.secrets_file}.example")

        lines.append("")
        lines.append("Environment variables:")
        env_vars = [
            "VCF_ESXI_ROOT_PASSWORD",
            "VCF_INSTALLER_ROOT_PASSWORD",
            "VCF_INSTALLER_ADMIN_PASSWORD",
            "VCF_VCENTER_PASSWORD"
        ]
        for var in env_vars:
            if os.environ.get(var):
                lines.append(f"  ✓ {var} is set")
            else:
                lines.append(f"    {var} not set")

        return "\n".join(lines)


def load_config_with_secrets(config_file: Path) -> Dict[str, Any]:
    """
    Load config file and merge with secrets

    This function loads the main config file and replaces password placeholders
    with actual values from secure sources.
    """
    if not config_file.exists():
        print(f"ERROR: Config file not found: {config_file}")
        sys.exit(1)

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        print(f"ERROR: Failed to load config: {e}")
        sys.exit(1)

    # Initialize secrets manager
    project_dir = config_file.parent.parent
    secrets_mgr = SecretsManager(project_dir)

    # Replace passwords with secure values
    if 'common' in config:
        config['common']['root_password'] = secrets_mgr.get_esxi_root_password(
            config['common'].get('root_password')
        )

    if 'vcf_installer' in config:
        config['vcf_installer']['root_password'] = secrets_mgr.get_vcf_installer_root_password(
            config['vcf_installer'].get('root_password')
        )
        config['vcf_installer']['admin_password'] = secrets_mgr.get_vcf_installer_admin_password(
            config['vcf_installer'].get('admin_password')
        )

    if 'vcenter' in config:
        config['vcenter']['password'] = secrets_mgr.get_vcenter_password(
            config['vcenter'].get('password')
        )

    return config
