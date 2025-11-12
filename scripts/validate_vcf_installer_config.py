#!/usr/bin/env python3
"""
VCF Installer Configuration Validator
Purpose: Verify that setup_vcf_installer.py successfully configured the VCF Installer VM
Author: Auto-generated for VCF 9.x in a Box project
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim

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


class VCFInstallerValidator:
    """Validate VCF Installer configuration"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.vcf_installer = config["vcf_installer"]
        self.common = config["common"]

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

        self.si: Optional[vim.ServiceInstance] = None
        self.vm: Optional[vim.VirtualMachine] = None

    def connect_esxi(self) -> bool:
        """Connect to ESXi host"""
        try:
            print(f"{Colors.YELLOW}Connecting to ESXi host {self.target_host['hostname']}...{Colors.NC}")

            self.si = SmartConnect(
                host=self.target_host["ip"],
                user="root",
                pwd=self.common["root_password"],
                disableSslCertValidation=True,
            )

            print(f"{Colors.GREEN}✓ Connected to ESXi host{Colors.NC}\n")
            return True

        except (vim.fault.VimFault, IOError, OSError) as e:
            print(f"{Colors.RED}ERROR: Failed to connect to ESXi: {e}{Colors.NC}")
            return False

    def find_vm(self) -> bool:
        """Find VCF Installer VM"""
        try:
            content = self.si.RetrieveContent()
            container = content.rootFolder
            viewType = [vim.VirtualMachine]
            recursive = True

            containerView = content.viewManager.CreateContainerView(
                container, viewType, recursive
            )

            vms = containerView.view
            for vm in vms:
                if vm.name == self.vcf_installer["vm_name"]:
                    self.vm = vm
                    print(f"{Colors.GREEN}✓ Found VCF Installer VM: {vm.name}{Colors.NC}\n")
                    return True

            print(f"{Colors.RED}ERROR: VM not found: {self.vcf_installer['vm_name']}{Colors.NC}")
            return False

        except (vim.fault.VimFault, AttributeError) as e:
            print(f"{Colors.RED}ERROR: Failed to find VM: {e}{Colors.NC}")
            return False

    def execute_command(self, command: str, timeout: int = 10) -> Tuple[int, str]:
        """Execute command in guest and return exit code and output"""
        try:
            # Create credentials
            creds = vim.vm.guest.NamePasswordAuthentication(
                username="root", password=self.vcf_installer["root_password"]
            )

            # Get process manager
            content = self.si.RetrieveContent()
            process_manager = content.guestOperationsManager.processManager

            # Execute command
            spec = vim.vm.guest.ProcessManager.ProgramSpec(
                programPath="/bin/bash", arguments=f'-c "{command}"'
            )

            pid = process_manager.StartProgramInGuest(vm=self.vm, auth=creds, spec=spec)

            # Wait for completion
            for _ in range(timeout * 2):  # Check every 0.5 seconds
                processes = process_manager.ListProcessesInGuest(
                    vm=self.vm, auth=creds, pids=[pid]
                )
                if processes and processes[0].endTime:
                    return processes[0].exitCode, ""

                time.sleep(0.5)

            return -1, "Timeout"

        except Exception as e:
            return -1, str(e)

    def validate_nic_speed_validation(self) -> bool:
        """Validate NIC speed validation is disabled"""
        print(f"{Colors.BLUE}Checking NIC speed validation...{Colors.NC}")

        if not self.vcf_installer.get("features", {}).get("skip_nic_speed_validation", False):
            print(
                f"{Colors.YELLOW}  ℹ NIC speed validation not configured (not enabled in config){Colors.NC}\n"
            )
            return True

        cmd = 'grep -q "enable.speed.of.physical.nics.validation=false" /opt/vmware/vcf/domainmanager/conf/application.properties'
        exit_code, _ = self.execute_command(cmd)

        if exit_code == 0:
            print(
                f"{Colors.GREEN}  ✓ NIC speed validation is disabled{Colors.NC}"
            )
            return True
        else:
            print(
                f"{Colors.RED}  ✗ NIC speed validation setting NOT found{Colors.NC}"
            )
            return False

    def validate_single_host_domain(self) -> bool:
        """Validate single-host domain feature is enabled"""
        print(f"{Colors.BLUE}Checking single-host domain feature...{Colors.NC}")

        if not self.vcf_installer.get("features", {}).get("single_host_domain", False):
            print(
                f"{Colors.YELLOW}  ℹ Single-host domain not configured (not enabled in config){Colors.NC}\n"
            )
            return True

        cmd = 'grep -q "feature.vcf.internal.single.host.domain=true" /home/vcf/feature.properties'
        exit_code, _ = self.execute_command(cmd)

        if exit_code == 0:
            print(
                f"{Colors.GREEN}  ✓ Single-host domain feature is enabled{Colors.NC}"
            )
            return True
        else:
            print(
                f"{Colors.RED}  ✗ Single-host domain feature NOT found{Colors.NC}"
            )
            return False

    def validate_offline_depot(self) -> bool:
        """Validate offline depot is configured"""
        print(f"{Colors.BLUE}Checking offline depot configuration...{Colors.NC}")

        depot = self.vcf_installer.get("depot", {})
        if depot.get("type") != "offline":
            print(
                f"{Colors.YELLOW}  ℹ Offline depot not configured (not set to offline in config){Colors.NC}\n"
            )
            return True

        if depot.get("use_https", True):
            print(
                f"{Colors.YELLOW}  ℹ Offline depot using HTTPS (default){Colors.NC}\n"
            )
            return True

        cmd = 'grep -q "lcm.depot.adapter.httpsEnabled=false" /opt/vmware/vcf/lcm/lcm-app/conf/application-prod.properties'
        exit_code, _ = self.execute_command(cmd)

        if exit_code == 0:
            print(
                f"{Colors.GREEN}  ✓ Offline depot configured for HTTP{Colors.NC}"
            )
            return True
        else:
            print(
                f"{Colors.RED}  ✗ Offline depot HTTP setting NOT found{Colors.NC}"
            )
            return False

    def validate_feature_file_permissions(self) -> bool:
        """Validate feature.properties file has correct permissions"""
        print(f"{Colors.BLUE}Checking feature.properties permissions...{Colors.NC}")

        cmd = 'test -r /home/vcf/feature.properties && echo "OK"'
        exit_code, _ = self.execute_command(cmd)

        if exit_code == 0:
            print(
                f"{Colors.GREEN}  ✓ Feature file exists and is readable{Colors.NC}"
            )
            return True
        else:
            print(f"{Colors.RED}  ✗ Feature file not found or not readable{Colors.NC}")
            return False

    def validate_services_restarted(self) -> bool:
        """Check if VCF services are running"""
        print(f"{Colors.BLUE}Checking VCF services status...{Colors.NC}")

        services = ["vcf-lcm", "vcf-domainmanager"]
        all_running = True

        for service in services:
            cmd = f'systemctl is-active {service}'
            exit_code, _ = self.execute_command(cmd)

            if exit_code == 0:
                print(f"{Colors.GREEN}  ✓ {service} is running{Colors.NC}")
            else:
                print(f"{Colors.RED}  ✗ {service} is NOT running{Colors.NC}")
                all_running = False

        return all_running

    def disconnect(self):
        """Disconnect from ESXi"""
        if self.si:
            try:
                Disconnect(self.si)
                print(f"\n{Colors.GREEN}✓ Disconnected from ESXi host{Colors.NC}\n")
            except (vim.fault.VimFault, IOError):
                pass

    def validate(self) -> bool:
        """Run all validation checks"""
        print(f"{Colors.GREEN}========================================{Colors.NC}")
        print(f"{Colors.GREEN}VCF Installer Configuration Validator{Colors.NC}")
        print(f"{Colors.GREEN}========================================{Colors.NC}\n")

        print(f"{Colors.BLUE}Configuration:{Colors.NC}")
        print(f"  VM Name:     {self.vcf_installer['vm_name']}")
        print(f"  Hostname:    {self.vcf_installer['hostname']}")
        print(f"  Target Host: {self.target_host['hostname']}\n")

        # Connect
        if not self.connect_esxi():
            return False

        # Find VM
        if not self.find_vm():
            return False

        print(f"{Colors.GREEN}========================================{Colors.NC}")
        print(f"{Colors.GREEN}Running Validation Checks{Colors.NC}")
        print(f"{Colors.GREEN}========================================{Colors.NC}\n")

        # Run validations
        results = []
        results.append(("NIC Speed Validation", self.validate_nic_speed_validation()))
        results.append(("Single-Host Domain", self.validate_single_host_domain()))
        results.append(("Offline Depot", self.validate_offline_depot()))
        results.append(("Feature File Permissions", self.validate_feature_file_permissions()))
        results.append(("VCF Services", self.validate_services_restarted()))

        # Summary
        print(f"\n{Colors.GREEN}========================================{Colors.NC}")
        print(f"{Colors.GREEN}Validation Summary{Colors.NC}")
        print(f"{Colors.GREEN}========================================{Colors.NC}\n")

        passed = sum(1 for _, result in results if result)
        total = len(results)

        for name, result in results:
            status = f"{Colors.GREEN}✓ PASS{Colors.NC}" if result else f"{Colors.RED}✗ FAIL{Colors.NC}"
            print(f"  {name:.<30} {status}")

        print(f"\n{Colors.BLUE}Results: {passed}/{total} checks passed{Colors.NC}\n")

        if passed == total:
            print(f"{Colors.GREEN}✓ All validation checks passed!{Colors.NC}")
            print(f"{Colors.GREEN}VCF Installer is properly configured.{Colors.NC}\n")
            return True
        else:
            print(f"{Colors.YELLOW}⚠ Some validation checks failed.{Colors.NC}")
            print(f"{Colors.YELLOW}You may need to re-run: make setup-vcf-installer{Colors.NC}\n")
            return False


def main():
    """
    Validate VCF Installer configuration.

    This script verifies that the setup_vcf_installer.py script successfully
    configured the VCF Installer VM by checking:
    - NIC speed validation disabled
    - Single-host domain feature enabled
    - Offline depot configured
    - Feature file permissions
    - VCF services running
    """
    parser = argparse.ArgumentParser(
        description="Validate VCF Installer configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Validate VCF Installer configuration
  %(prog)s --config custom.yaml     # Use custom config file

This script uses VMware Guest Operations API to read configuration
files as root, bypassing SSH restrictions.
        """,
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

    # Create validator
    validator = VCFInstallerValidator(config)

    try:
        # Validate
        success = validator.validate()
        sys.exit(0 if success else 1)
    finally:
        validator.disconnect()


if __name__ == "__main__":
    main()
