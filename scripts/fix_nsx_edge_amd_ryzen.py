#!/usr/bin/env python3
# ABOUTME: Fixes NSX Edge VMs to run on AMD Ryzen CPUs by disabling CPU validation
# ABOUTME: Required for VCF 9.0.1 deployments on consumer AMD Ryzen processors
"""
NSX Edge AMD Ryzen CPU Fix Script
Purpose: Disable CPU validation that blocks NSX Edge on non-EPYC AMD processors
Author: Modernized from William Lam's workaround

IMPORTANT: This script is needed for AMD Ryzen deployments where NSX Edge
VMs will fail to start the dataplane service due to CPU validation.

For VCF 9.0.1, the file path is /os_bak/opt/vmware/nsx-edge/bin/config.py
(differs from earlier versions which use /opt/vmware/nsx-edge/bin/config.py)

Reference: https://williamlam.com/2020/05/configure-nsx-t-edge-to-run-on-amd-ryzen-cpu.html
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import paramiko

# Add scripts directory to path for vcf_secrets import
sys.path.insert(0, str(Path(__file__).parent))

# pylint: disable=wrong-import-position
from vcf_secrets import load_config_with_secrets


# Color output
# pylint: disable=too-few-public-methods
class Colors:
    """ANSI color codes for terminal output"""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color


def load_config(config_file: Path) -> Dict[str, Any]:
    """Load configuration from YAML file with secrets"""
    return load_config_with_secrets(config_file)


class NSXEdgeAMDFixer:
    """Fix NSX Edge VMs to run on AMD Ryzen CPUs"""

    # VCF 9.0.1 uses /os_bak path during deployment
    CONFIG_FILE_PATH = "/os_bak/opt/vmware/nsx-edge/bin/config.py"
    # Alternative path for already-deployed edges
    ALT_CONFIG_FILE_PATH = "/opt/vmware/nsx-edge/bin/config.py"

    def __init__(
        self,
        config: Dict[str, Any],
        edge_password: str,
        edge_hosts: Optional[List[str]] = None,
    ):
        self.config = config
        self.edge_password = edge_password
        # Use provided edge hosts or defaults from network config
        self.edge_hosts = edge_hosts or self._get_default_edge_hosts()

    def _get_default_edge_hosts(self) -> List[str]:
        """Get default edge hosts from config or use standard IPs"""
        # Check if nsx_edges is defined in config
        if "nsx_edges" in self.config:
            return [edge["ip"] for edge in self.config["nsx_edges"]]

        # Fall back to standard VCF lab IPs
        return ["172.30.0.17", "172.30.0.18"]

    def wait_for_ssh(
        self, host: str, timeout: int = 600, interval: int = 30
    ) -> bool:
        """Wait for SSH to become available on the edge VM"""
        elapsed = 0

        print(
            f"{Colors.YELLOW}⏳ Waiting for SSH on {host}...{Colors.NC}"
        )

        while elapsed < timeout:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(
                    host,
                    username="admin",
                    password=self.edge_password,
                    timeout=10,
                    allow_agent=False,
                    look_for_keys=False,
                )
                ssh.close()
                print(f"{Colors.GREEN}✓ SSH available on {host}{Colors.NC}")
                return True

            except Exception:
                pass

            if elapsed > 0:
                print(
                    f"{Colors.YELLOW}⏳ SSH not ready on {host}. "
                    f"Retrying in {interval}s... "
                    f"(elapsed: {elapsed}/{timeout}s){Colors.NC}"
                )
            time.sleep(interval)
            elapsed += interval

        print(f"{Colors.RED}ERROR: Timeout waiting for SSH on {host}{Colors.NC}")
        return False

    def check_config_file_exists(self, ssh: paramiko.SSHClient, host: str) -> Optional[str]:
        """Check which config file path exists and return it"""
        for path in [self.CONFIG_FILE_PATH, self.ALT_CONFIG_FILE_PATH]:
            stdin, stdout, stderr = ssh.exec_command(f"test -f {path} && echo exists")
            if stdout.read().decode().strip() == "exists":
                print(f"{Colors.BLUE}Found config file at: {path}{Colors.NC}")
                return path

        print(f"{Colors.RED}ERROR: config.py not found on {host}{Colors.NC}")
        return None

    def check_already_fixed(self, ssh: paramiko.SSHClient, config_path: str) -> bool:
        """Check if the fix has already been applied"""
        # Look for commented-out AMD check line
        cmd = f"grep -c '#.*if.*AMD.*in.*vendor_info' {config_path} 2>/dev/null || echo 0"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        count = stdout.read().decode().strip()

        return int(count) > 0

    def apply_fix(
        self, ssh: paramiko.SSHClient, host: str, config_path: str, dry_run: bool = False
    ) -> bool:
        """Apply the AMD Ryzen fix to config.py"""
        try:
            # Check if already fixed
            if self.check_already_fixed(ssh, config_path):
                print(
                    f"{Colors.YELLOW}⚠ Fix already applied on {host}, skipping{Colors.NC}"
                )
                return True

            if dry_run:
                print(
                    f"{Colors.YELLOW}DRY RUN: Would comment out AMD EPYC validation "
                    f"in {config_path} on {host}{Colors.NC}"
                )
                return True

            # Create backup
            backup_cmd = f"cp {config_path} {config_path}.bak"
            ssh.exec_command(backup_cmd)

            # Use sed to comment out the two lines
            # Line 1: if "AMD" in vendor_info and "AMD EPYC" not in model_name:
            # Line 2: self.error_exit("Unsupported CPU: %s" % model_name)
            sed_cmd = (
                f"sed -i "
                f"-e 's/^\\(\\s*\\)\\(if \"AMD\" in vendor_info and \"AMD EPYC\" not in model_name:\\)/\\1# \\2/' "
                f"-e 's/^\\(\\s*\\)\\(self\\.error_exit(\"Unsupported CPU:.*model_name)\\)/\\1# \\2/' "
                f"{config_path}"
            )

            stdin, stdout, stderr = ssh.exec_command(sed_cmd)
            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0:
                error = stderr.read().decode()
                print(f"{Colors.RED}ERROR: sed command failed: {error}{Colors.NC}")
                return False

            # Verify the fix was applied
            if not self.check_already_fixed(ssh, config_path):
                print(
                    f"{Colors.RED}ERROR: Fix verification failed on {host}{Colors.NC}"
                )
                return False

            print(
                f"{Colors.GREEN}✓ AMD EPYC validation commented out on {host}{Colors.NC}"
            )
            return True

        except Exception as e:
            print(f"{Colors.RED}ERROR: Failed to apply fix on {host}: {e}{Colors.NC}")
            return False

    def restart_dataplane(
        self, ssh: paramiko.SSHClient, host: str, dry_run: bool = False
    ) -> bool:
        """Restart the dataplane service to apply the fix"""
        if dry_run:
            print(
                f"{Colors.YELLOW}DRY RUN: Would restart dataplane service on {host}{Colors.NC}"
            )
            return True

        print(f"{Colors.YELLOW}Restarting dataplane service on {host}...{Colors.NC}")

        # The command to restart dataplane
        cmd = "start service dataplane"

        try:
            stdin, stdout, stderr = ssh.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()

            # Read streams (stdout unused, but must be consumed)
            stdout.read()
            error = stderr.read().decode()

            if exit_status != 0:
                print(
                    f"{Colors.RED}ERROR: Failed to restart dataplane on {host}: "
                    f"{error}{Colors.NC}"
                )
                return False

            print(
                f"{Colors.GREEN}✓ Dataplane service restart initiated on {host}{Colors.NC}"
            )
            print(f"{Colors.BLUE}Note: Edge VM will reboot automatically{Colors.NC}")
            return True

        except Exception as e:
            print(
                f"{Colors.RED}ERROR: Failed to restart dataplane on {host}: {e}{Colors.NC}"
            )
            return False

    def fix_edge(self, host: str, dry_run: bool = False) -> bool:
        """Apply the fix to a single edge VM"""
        print(f"\n{Colors.BLUE}Processing edge: {host}{Colors.NC}")
        print("-" * 40)

        # Wait for SSH
        if not dry_run and not self.wait_for_ssh(host):
            return False

        try:
            # Connect via SSH
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if not dry_run:
                ssh.connect(
                    host,
                    username="admin",
                    password=self.edge_password,
                    timeout=30,
                    allow_agent=False,
                    look_for_keys=False,
                )

                # Find the config file
                config_path = self.check_config_file_exists(ssh, host)
                if not config_path:
                    ssh.close()
                    return False
            else:
                config_path = self.CONFIG_FILE_PATH
                print(
                    f"{Colors.YELLOW}DRY RUN: Would connect to {host} as admin{Colors.NC}"
                )

            # Apply the fix
            if not self.apply_fix(ssh, host, config_path, dry_run):
                if not dry_run:
                    ssh.close()
                return False

            # Restart dataplane
            if not self.restart_dataplane(ssh, host, dry_run):
                if not dry_run:
                    ssh.close()
                return False

            if not dry_run:
                ssh.close()

            return True

        except paramiko.AuthenticationException:
            print(
                f"{Colors.RED}ERROR: Authentication failed for {host}. "
                f"Check the edge password.{Colors.NC}"
            )
            return False
        except Exception as e:
            print(f"{Colors.RED}ERROR: Failed to process {host}: {e}{Colors.NC}")
            return False

    def run(self, dry_run: bool = False, wait_between: int = 60) -> bool:
        """Run the fix on all edge VMs"""
        print(f"{Colors.GREEN}========================================{Colors.NC}")
        print(f"{Colors.GREEN}NSX Edge AMD Ryzen CPU Fix{Colors.NC}")
        print(f"{Colors.GREEN}========================================{Colors.NC}\n")

        if dry_run:
            print(f"{Colors.YELLOW}DRY RUN MODE - No changes will be made{Colors.NC}\n")

        print(f"{Colors.BLUE}Configuration:{Colors.NC}")
        print(f"  Edge VMs:      {', '.join(self.edge_hosts)}")
        print(f"  Config Path:   {self.CONFIG_FILE_PATH}")
        print("  Fix:           Comment out AMD EPYC CPU validation")
        print()

        all_success = True

        for i, host in enumerate(self.edge_hosts):
            success = self.fix_edge(host, dry_run)
            if not success:
                all_success = False
                print(
                    f"{Colors.RED}✗ Failed to fix edge {host}{Colors.NC}"
                )
            else:
                print(f"{Colors.GREEN}✓ Edge {host} processed successfully{Colors.NC}")

            # Wait between edges (not after last one)
            if not dry_run and i < len(self.edge_hosts) - 1:
                print(
                    f"\n{Colors.YELLOW}Waiting {wait_between}s before processing "
                    f"next edge...{Colors.NC}"
                )
                time.sleep(wait_between)

        print()
        if all_success:
            print(f"{Colors.GREEN}========================================{Colors.NC}")
            print(f"{Colors.GREEN}NSX Edge AMD Ryzen Fix Complete!{Colors.NC}")
            print(f"{Colors.GREEN}========================================{Colors.NC}\n")

            print(f"{Colors.BLUE}Next Steps:{Colors.NC}")
            print("  - Edge VMs will reboot automatically")
            print("  - Wait 5-10 minutes for edges to come back online")
            print("  - VCF deployment should continue normally")
            print("  - Monitor deployment progress in VCF Installer UI")
            print()
        else:
            print(f"{Colors.RED}========================================{Colors.NC}")
            print(f"{Colors.RED}Some edges failed - check errors above{Colors.NC}")
            print(f"{Colors.RED}========================================{Colors.NC}\n")

        return all_success


def main():
    parser = argparse.ArgumentParser(
        description="Fix NSX Edge VMs to run on AMD Ryzen CPUs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --password 'EdgePassword123!'
  %(prog)s --password 'EdgePassword123!' --dry-run
  %(prog)s --password 'EdgePassword123!' --edges 172.30.0.17 172.30.0.18
  %(prog)s --password 'EdgePassword123!' --config custom.yaml

IMPORTANT:
  - Run this script DURING VCF network connectivity deployment
  - The Edge VMs must be powered on and accessible via SSH
  - For VCF 9.0.1, this modifies /os_bak/opt/vmware/nsx-edge/bin/config.py
  - After the fix, the dataplane service restarts and Edge VMs reboot
  - Wait for edges to come back online before deployment continues

Reference:
  https://williamlam.com/2020/05/configure-nsx-t-edge-to-run-on-amd-ryzen-cpu.html
        """,
    )

    parser.add_argument(
        "-p",
        "--password",
        required=True,
        help="NSX Edge admin password (from VCF deployment manifest)",
    )

    parser.add_argument(
        "-d", "--dry-run", action="store_true", help="Preview changes without executing"
    )

    parser.add_argument(
        "-e",
        "--edges",
        nargs="+",
        help="Edge VM hostnames or IPs (default: 172.30.0.17, 172.30.0.18)",
    )

    parser.add_argument(
        "-w",
        "--wait",
        type=int,
        default=60,
        help="Seconds to wait between processing edges (default: 60)",
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

    # Load configuration
    config = load_config(config_file)

    # Create fixer
    fixer = NSXEdgeAMDFixer(
        config=config,
        edge_password=args.password,
        edge_hosts=args.edges,
    )

    # Run
    success = fixer.run(dry_run=args.dry_run, wait_between=args.wait)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
