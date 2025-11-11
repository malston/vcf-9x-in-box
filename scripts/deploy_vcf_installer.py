#!/usr/bin/env python3
"""
VCF Installer Deployment Script
Purpose: Deploy VCF Installer OVA to ESXi host using OVFTool
Author: Modernized from William Lam's bash script
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List

# Add scripts directory to path for vcf_secrets import
sys.path.insert(0, str(Path(__file__).parent))

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml module not found. Install with: uv sync")
    sys.exit(1)

from vcf_secrets import load_config_with_secrets


# Color output
class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color


def validate_config_keys(config: Dict[str, Any]) -> None:
    """Validate that all required configuration keys exist"""
    errors = []

    # Validate network section
    required_network_keys = ["netmask", "gateway", "dns_server", "dns_domain"]
    for key in required_network_keys:
        if key not in config["network"]:
            errors.append(f"Missing 'network.{key}' in config file")

    # Validate common section
    required_common_keys = ["ovftool_path", "root_password", "ntp_server"]
    for key in required_common_keys:
        if key not in config["common"]:
            errors.append(f"Missing 'common.{key}' in config file")

    # Validate vcf_installer section
    required_vcf_keys = [
        "ova_path",
        "vm_name",
        "hostname",
        "ip",
        "root_password",
        "admin_password",
        "target_host",
        "vm_network",
    ]
    for key in required_vcf_keys:
        if key not in config["vcf_installer"]:
            errors.append(f"Missing 'vcf_installer.{key}' in config file")

    # Validate hosts section
    if not config.get("hosts") or not isinstance(config["hosts"], list):
        errors.append("'hosts' must be a non-empty list")
    else:
        required_host_keys = ["number", "hostname", "ip", "datastore_name"]
        for idx, host in enumerate(config["hosts"]):
            for key in required_host_keys:
                if key not in host:
                    errors.append(f"Missing 'hosts[{idx}].{key}' in config file")

    # Report all errors at once
    if errors:
        print(f"{Colors.RED}ERROR: Configuration validation failed:{Colors.NC}")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)


class VCFInstallerDeployer:
    """Deploy VCF Installer OVA to ESXi host"""

    def __init__(self, script_dir: Path, config: Dict[str, Any]):
        self.script_dir = script_dir
        self.project_dir = script_dir.parent
        self.config = config

        # Get configuration values
        self.ovftool_path = config["common"]["ovftool_path"]
        self.vcf_installer = config["vcf_installer"]
        self.network = config["network"]

        # Determine target host
        target_host_num = self.vcf_installer["target_host"]
        self.target_host = None
        for host in config["hosts"]:
            if host["number"] == target_host_num:
                self.target_host = host
                break

        if not self.target_host:
            print(
                f"{Colors.RED}ERROR: Target host {target_host_num} not found in config{Colors.NC}"
            )
            sys.exit(1)

    def validate_prerequisites(self) -> bool:
        """Validate all prerequisites before deployment"""
        print(f"{Colors.YELLOW}Validating prerequisites...{Colors.NC}\n")

        all_valid = True

        # Check ovftool exists
        ovftool = Path(self.ovftool_path)
        if not ovftool.exists():
            print(f"{Colors.RED}✗ OVFTool not found: {ovftool}{Colors.NC}")
            all_valid = False
        elif not ovftool.is_file():
            print(f"{Colors.RED}✗ OVFTool is not a file: {ovftool}{Colors.NC}")
            all_valid = False
        else:
            print(f"{Colors.GREEN}✓ OVFTool found: {ovftool}{Colors.NC}")

        # Check OVA file exists
        ova_path = Path(self.vcf_installer["ova_path"])
        if not ova_path.exists():
            print(f"{Colors.RED}✗ VCF Installer OVA not found: {ova_path}{Colors.NC}")
            all_valid = False
        else:
            # Get OVA size in MB
            ova_size_mb = ova_path.stat().st_size / (1024 * 1024)
            print(
                f"{Colors.GREEN}✓ VCF Installer OVA found: {ova_path} ({ova_size_mb:.1f} MB){Colors.NC}"
            )

        print()
        return all_valid

    def build_ovftool_command(self) -> List[str]:
        """Build the ovftool command with all parameters"""
        vcf = self.vcf_installer
        target = self.target_host
        network = self.network
        common = self.config["common"]

        # ESXi target URL
        esxi_url = f"vi://root:{common['root_password']}@{target['ip']}/"

        # Build command
        cmd = [
            self.ovftool_path,
            "--acceptAllEulas",
            "--noSSLVerify",
            "--skipManifestCheck",
            "--X:injectOvfEnv",
            "--allowExtraConfig",
            "--X:waitForIp",
            "--sourceType=OVA",
            "--powerOn",
            f"--net:Network 1={vcf['vm_network']}",
            f"--datastore={target['datastore_name']}",
            "--diskMode=thin",
            f"--name={vcf['vm_name']}",
            f"--prop:vami.hostname={vcf['hostname']}",
            f"--prop:vami.ip0.SDDC-Manager={vcf['ip']}",
            f"--prop:vami.netmask0.SDDC-Manager={network['netmask']}",
            f"--prop:vami.gateway.SDDC-Manager={network['gateway']}",
            f"--prop:vami.domain.SDDC-Manager={network['dns_domain']}",
            f"--prop:vami.searchpath.SDDC-Manager={network['dns_domain']}",
            f"--prop:vami.DNS.SDDC-Manager={network['dns_server']}",
            f"--prop:ROOT_PASSWORD={vcf['root_password']}",
            f"--prop:LOCAL_USER_PASSWORD={vcf['admin_password']}",
            f"--prop:guestinfo.ntp={common['ntp_server']}",
            vcf["ova_path"],
            esxi_url,
        ]

        return cmd

    def deploy(self, dry_run: bool = False) -> bool:
        """Deploy VCF Installer OVA"""
        # Validate prerequisites
        if not self.validate_prerequisites():
            print(f"{Colors.RED}ERROR: Prerequisites validation failed{Colors.NC}")
            return False

        # Build command
        cmd = self.build_ovftool_command()

        # Print deployment information
        print(f"{Colors.GREEN}========================================{Colors.NC}")
        print(f"{Colors.GREEN}VCF Installer Deployment{Colors.NC}")
        print(f"{Colors.GREEN}========================================{Colors.NC}\n")

        print(f"{Colors.BLUE}Configuration:{Colors.NC}")
        print(f"  VM Name:     {self.vcf_installer['vm_name']}")
        print(f"  Hostname:    {self.vcf_installer['hostname']}")
        print(f"  IP Address:  {self.vcf_installer['ip']}")
        print(
            f"  Target Host: {self.target_host['hostname']} ({self.target_host['ip']})"
        )
        print(f"  Datastore:   {self.target_host['datastore_name']}")
        print(f"  Network:     {self.vcf_installer['vm_network']}")
        print()

        if dry_run:
            print(f"{Colors.YELLOW}========================================{Colors.NC}")
            print(f"{Colors.YELLOW}DRY RUN MODE - No deployment will occur{Colors.NC}")
            print(
                f"{Colors.YELLOW}========================================{Colors.NC}\n"
            )

            print(f"{Colors.YELLOW}Command that would be executed:{Colors.NC}")
            # Mask password in display
            display_cmd = []
            for arg in cmd:
                if "root_password" in str(arg) or "PASSWORD" in str(arg):
                    # Mask the password
                    if "=" in arg:
                        key, _ = arg.split("=", 1)
                        display_cmd.append(f"{key}=********")
                    elif "@" in arg:
                        # Mask password in URL
                        display_cmd.append(
                            arg.replace(
                                self.config["common"]["root_password"], "********"
                            )
                        )
                    else:
                        display_cmd.append(arg)
                else:
                    display_cmd.append(arg)

            print(" \\\n  ".join(display_cmd))
            print()
            return True

        # Deploy
        print(
            f"{Colors.YELLOW}Deploying VCF Installer {self.vcf_installer['vm_name']}...{Colors.NC}"
        )
        print(f"{Colors.YELLOW}This may take 10-15 minutes...{Colors.NC}\n")

        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)

            print(result.stdout)

            print(
                f"\n{Colors.GREEN}========================================{Colors.NC}"
            )
            print(f"{Colors.GREEN}Deployment Complete!{Colors.NC}")
            print(
                f"{Colors.GREEN}========================================{Colors.NC}\n"
            )

            print(f"{Colors.BLUE}Next Steps:{Colors.NC}")
            print(
                f"  1. Access VCF Installer UI: https://{self.vcf_installer['hostname']}/"
            )
            print(
                f"  2. Run: {Colors.YELLOW}uv run scripts/setup_vcf_installer.py{Colors.NC}"
            )
            print()

            return True

        except subprocess.CalledProcessError as e:
            print(f"\n{Colors.RED}ERROR: OVFTool deployment failed{Colors.NC}")
            print(f"{Colors.RED}Exit code: {e.returncode}{Colors.NC}")
            if e.stdout:
                print(f"\n{Colors.YELLOW}STDOUT:{Colors.NC}")
                print(e.stdout)
            if e.stderr:
                print(f"\n{Colors.YELLOW}STDERR:{Colors.NC}")
                print(e.stderr)
            return False
        except Exception as e:
            print(
                f"\n{Colors.RED}ERROR: Unexpected error during deployment: {e}{Colors.NC}"
            )
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Deploy VCF Installer OVA to ESXi host",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Deploy VCF Installer
  %(prog)s --dry-run                # Preview deployment without executing
  %(prog)s --config custom.yaml    # Use custom config file

Requirements:
  - VMware OVFTool must be installed
  - Target ESXi host must be accessible
  - VCF Installer OVA must be available
        """,
    )

    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Preview deployment without executing",
    )

    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="Path to YAML config file (default: config/vcf-config.yaml)",
    )

    args = parser.parse_args()

    # Determine directories
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent

    # Determine config file
    config_file = (
        args.config if args.config else project_dir / "config" / "vcf-config.yaml"
    )

    # Load configuration with secrets
    config = load_config_with_secrets(config_file)

    # Validate configuration structure
    validate_config_keys(config)

    # Print header
    print(f"{Colors.GREEN}========================================{Colors.NC}")
    print(f"{Colors.GREEN}VCF Installer Deployment Tool{Colors.NC}")
    print(f"{Colors.GREEN}========================================{Colors.NC}\n")

    # Create deployer
    deployer = VCFInstallerDeployer(script_dir, config)

    # Deploy
    success = deployer.deploy(dry_run=args.dry_run)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
