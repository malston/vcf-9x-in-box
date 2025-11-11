#!/usr/bin/env python3
"""
ESXi SSH Key Setup Script
Purpose: Generate SSH keys, update SSH config, and copy keys to ESXi hosts
Author: Auto-generated for VCF 9.x in a Box project
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml module not found. Install with: uv sync")
    sys.exit(1)


# Color output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


def print_message(color: str, message: str):
    """Print colored message"""
    print(f"{color}{message}{Colors.NC}")


def load_config(config_file: Path) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    if not config_file.exists():
        print_message(Colors.RED, f"ERROR: Config file not found: {config_file}")
        sys.exit(1)

    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        # Validate required sections
        required_sections = ['common', 'hosts']
        for section in required_sections:
            if section not in config:
                print_message(Colors.RED, f"ERROR: Missing '{section}' section in config file")
                sys.exit(1)

        return config

    except yaml.YAMLError as e:
        print_message(Colors.RED, f"ERROR: Failed to parse YAML config: {e}")
        sys.exit(1)
    except Exception as e:
        print_message(Colors.RED, f"ERROR: Failed to load config: {e}")
        sys.exit(1)


class ESXiSSHKeySetup:
    """Setup SSH keys for ESXi hosts"""

    def __init__(self, config: Dict[str, Any], key_name: str = "vcf-esxi"):
        self.config = config
        self.key_name = key_name
        self.ssh_dir = Path.home() / ".ssh"
        self.private_key_path = self.ssh_dir / key_name
        self.public_key_path = self.ssh_dir / f"{key_name}.pub"
        self.ssh_config_path = self.ssh_dir / "config"
        self.root_password = config['common']['root_password']

    def setup(self, dry_run: bool = False) -> bool:
        """Run complete SSH key setup"""
        print_message(Colors.GREEN, "========================================")
        print_message(Colors.GREEN, "ESXi SSH Key Setup")
        print_message(Colors.GREEN, "========================================\n")

        if dry_run:
            print_message(Colors.YELLOW, "========================================")
            print_message(Colors.YELLOW, "DRY RUN MODE - No changes will be made")
            print_message(Colors.YELLOW, "========================================\n")

        # Step 1: Generate SSH key
        if not self._generate_ssh_key(dry_run):
            return False

        # Step 2: Update SSH config
        if not self._update_ssh_config(dry_run):
            return False

        # Step 3: Copy public key to ESXi hosts
        if not self._copy_keys_to_hosts(dry_run):
            return False

        # Print success message
        print_message(Colors.GREEN, "\n========================================")
        print_message(Colors.GREEN, "SSH Key Setup Complete!")
        print_message(Colors.GREEN, "========================================\n")

        print_message(Colors.BLUE, "You can now SSH to hosts using:")
        for host in self.config['hosts']:
            hostname = host['hostname'].split('.')[0]  # Get short name (esx01)
            print(f"  ssh {hostname}")
        print()

        return True

    def _generate_ssh_key(self, dry_run: bool) -> bool:
        """Generate SSH key pair if it doesn't exist"""
        print_message(Colors.YELLOW, "Step 1/3: Generating SSH key pair...")

        if self.private_key_path.exists() and self.public_key_path.exists():
            print_message(Colors.GREEN, f"✓ SSH key already exists: {self.private_key_path}")
            return True

        if dry_run:
            print_message(Colors.BLUE, f"[DRY RUN] Would generate SSH key: {self.private_key_path}")
            print_message(Colors.BLUE, f"[DRY RUN] Command: ssh-keygen -t rsa -b 4096 -f {self.private_key_path} -N ''")
            return True

        # Create .ssh directory if it doesn't exist
        self.ssh_dir.mkdir(mode=0o700, exist_ok=True)

        # Generate key
        try:
            subprocess.run(
                [
                    "ssh-keygen",
                    "-t", "rsa",
                    "-b", "4096",
                    "-f", str(self.private_key_path),
                    "-N", "",  # No passphrase
                    "-C", f"vcf-esxi-key"
                ],
                check=True,
                capture_output=True,
                text=True
            )
            print_message(Colors.GREEN, f"✓ SSH key generated: {self.private_key_path}")
            return True

        except subprocess.CalledProcessError as e:
            print_message(Colors.RED, f"ERROR: Failed to generate SSH key: {e}")
            if e.stderr:
                print(e.stderr)
            return False

    def _update_ssh_config(self, dry_run: bool) -> bool:
        """Update SSH config file with host entries"""
        print_message(Colors.YELLOW, "\nStep 2/3: Updating SSH config...")

        # Build SSH config entries
        config_entries = self._build_ssh_config_entries()

        if dry_run:
            print_message(Colors.BLUE, f"[DRY RUN] Would update: {self.ssh_config_path}")
            print_message(Colors.BLUE, "[DRY RUN] Entries to add:")
            print(config_entries)
            return True

        # Read existing config
        existing_config = ""
        if self.ssh_config_path.exists():
            existing_config = self.ssh_config_path.read_text()

        # Check if our entries already exist
        marker_start = "# BEGIN VCF ESXi Hosts"
        marker_end = "# END VCF ESXi Hosts"

        if marker_start in existing_config:
            # Remove old entries
            start_idx = existing_config.find(marker_start)
            end_idx = existing_config.find(marker_end)
            if end_idx != -1:
                end_idx = existing_config.find('\n', end_idx) + 1
                existing_config = existing_config[:start_idx] + existing_config[end_idx:]

        # Add new entries
        new_config = existing_config.rstrip() + "\n\n" + config_entries

        # Write config
        try:
            self.ssh_config_path.write_text(new_config)
            self.ssh_config_path.chmod(0o600)
            print_message(Colors.GREEN, f"✓ SSH config updated: {self.ssh_config_path}")
            return True

        except Exception as e:
            print_message(Colors.RED, f"ERROR: Failed to update SSH config: {e}")
            return False

    def _build_ssh_config_entries(self) -> str:
        """Build SSH config entries for all ESXi hosts"""
        entries = ["# BEGIN VCF ESXi Hosts"]
        entries.append("# Auto-generated by setup_esxi_ssh_keys.py")
        entries.append("")

        for host in self.config['hosts']:
            hostname = host['hostname'].split('.')[0]  # Get short name (esx01)
            entries.extend([
                f"Host {hostname}",
                f"    HostName {host['ip']}",
                f"    User root",
                f"    IdentityFile {self.private_key_path}",
                f"    StrictHostKeyChecking no",
                f"    UserKnownHostsFile /dev/null",
                ""
            ])

        entries.append("# END VCF ESXi Hosts")
        return "\n".join(entries)

    def _copy_keys_to_hosts(self, dry_run: bool) -> bool:
        """Copy public key to authorized_keys on each ESXi host"""
        print_message(Colors.YELLOW, "\nStep 3/3: Copying public key to ESXi hosts...")

        # Read public key (or use placeholder in dry-run mode)
        if not self.public_key_path.exists():
            if dry_run:
                public_key = "ssh-rsa AAAAB3... (key would be generated)"
            else:
                print_message(Colors.RED, f"ERROR: Public key not found: {self.public_key_path}")
                return False
        else:
            public_key = self.public_key_path.read_text().strip()

        all_success = True
        for host in self.config['hosts']:
            hostname = host['hostname'].split('.')[0]
            ip = host['ip']

            if dry_run:
                print_message(Colors.BLUE, f"[DRY RUN] Would copy key to {hostname} ({ip})")
                continue

            print(f"  Copying key to {hostname} ({ip})...")

            try:
                # Use sshpass to provide password, then copy key
                # ESXi authorized_keys location: /etc/ssh/keys-root/authorized_keys

                # Build command to add key if it doesn't already exist
                # ESXi's /etc/ssh/keys-root directory already exists and permissions are managed by ESXi
                add_key_cmd = (
                    f"grep -qF '{public_key}' /etc/ssh/keys-root/authorized_keys 2>/dev/null || "
                    f"echo '{public_key}' >> /etc/ssh/keys-root/authorized_keys; "
                    f"chmod 600 /etc/ssh/keys-root/authorized_keys 2>/dev/null"
                )

                result = subprocess.run(
                    [
                        "sshpass", "-p", self.root_password,
                        "ssh",
                        "-o", "StrictHostKeyChecking=no",
                        "-o", "UserKnownHostsFile=/dev/null",
                        "-o", "LogLevel=ERROR",
                        f"root@{ip}",
                        add_key_cmd
                    ],
                    check=True,
                    capture_output=True,
                    text=True
                )

                print_message(Colors.GREEN, f"    ✓ Key copied to {hostname}")

            except subprocess.CalledProcessError as e:
                print_message(Colors.RED, f"    ✗ Failed to copy key to {hostname}: {e}")
                if e.stderr:
                    print(f"      {e.stderr}")
                all_success = False
            except FileNotFoundError:
                print_message(Colors.RED, "    ✗ 'sshpass' command not found. Install with: brew install sshpass")
                all_success = False
                break

        return all_success


def main():
    parser = argparse.ArgumentParser(
        description="Setup SSH keys for ESXi hosts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Setup SSH keys
  %(prog)s --dry-run                # Preview without making changes
  %(prog)s --config custom.yaml     # Use custom config file
  %(prog)s --key-name my-esxi-key   # Use custom key name

This script will:
  1. Generate an SSH key pair (if not exists)
  2. Update ~/.ssh/config with host entries
  3. Copy public key to each ESXi host's authorized_keys

After running, you can SSH to hosts using:
  ssh esx01
  ssh esx02
  ssh esx03

Requirements:
  - sshpass must be installed: brew install sshpass
  - ESXi hosts must be accessible with root password
        """
    )

    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Preview changes without executing"
    )

    parser.add_argument(
        "-c", "--config",
        type=Path,
        help="Path to YAML config file (default: config/vcf-config.yaml)"
    )

    parser.add_argument(
        "-k", "--key-name",
        default="vcf-esxi",
        help="SSH key name (default: vcf-esxi)"
    )

    args = parser.parse_args()

    # Determine directories
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent

    # Determine config file
    config_file = args.config if args.config else project_dir / "config" / "vcf-config.yaml"

    # Load configuration
    config = load_config(config_file)

    # Create setup manager
    setup = ESXiSSHKeySetup(config, key_name=args.key_name)

    # Run setup
    success = setup.setup(dry_run=args.dry_run)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
