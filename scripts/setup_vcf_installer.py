#!/usr/bin/env python3
"""
VCF Installer Configuration Script
Purpose: Configure VCF Installer post-deployment
Author: Modernized from William Lam's PowerShell script
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional
import tempfile
import urllib3

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml module not found. Install with: uv sync")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests module not found. Install with: uv sync")
    sys.exit(1)

try:
    from pyVim.connect import SmartConnect, Disconnect
    from pyVim.task import WaitForTask
    from pyVmomi import vim
except ImportError:
    print("ERROR: pyvmomi module not found. Install with: uv sync")
    sys.exit(1)

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# Color output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


def load_config(config_file: Path) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    if not config_file.exists():
        print(f"{Colors.RED}ERROR: Config file not found: {config_file}{Colors.NC}")
        sys.exit(1)

    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        # Validate required sections
        required_sections = ['network', 'common', 'hosts', 'vcf_installer']
        for section in required_sections:
            if section not in config:
                print(f"{Colors.RED}ERROR: Missing '{section}' section in config file{Colors.NC}")
                sys.exit(1)

        return config

    except yaml.YAMLError as e:
        print(f"{Colors.RED}ERROR: Failed to parse YAML config: {e}{Colors.NC}")
        sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}ERROR: Failed to load config: {e}{Colors.NC}")
        sys.exit(1)


class VCFInstallerConfigurator:
    """Configure VCF Installer post-deployment"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.vcf_installer = config['vcf_installer']
        self.common = config['common']

        # Determine target host
        target_host_num = self.vcf_installer['target_host']
        self.target_host = None
        for host in config['hosts']:
            if host['number'] == target_host_num:
                self.target_host = host
                break

        if not self.target_host:
            print(f"{Colors.RED}ERROR: Target host {target_host_num} not found in config{Colors.NC}")
            sys.exit(1)

        self.si: Optional[vim.ServiceInstance] = None
        self.vm: Optional[vim.VirtualMachine] = None

    def connect_to_esxi(self) -> bool:
        """Connect to ESXi host"""
        try:
            print(f"{Colors.YELLOW}Connecting to ESXi host {self.target_host['hostname']}...{Colors.NC}")

            self.si = SmartConnect(
                host=self.target_host['ip'],
                user='root',
                pwd=self.common['root_password'],
                disableSslCertValidation=True
            )

            print(f"{Colors.GREEN}✓ Connected to ESXi host{Colors.NC}\n")
            return True

        except Exception as e:
            print(f"{Colors.RED}ERROR: Failed to connect to ESXi: {e}{Colors.NC}")
            return False

    def wait_for_vcf_installer_ui(self, timeout: int = 1800) -> bool:
        """Wait for VCF Installer UI to be ready"""
        url = f"https://{self.vcf_installer['hostname']}/vcf-installer-ui/login"
        interval = 120  # Check every 2 minutes
        elapsed = 0

        print(f"{Colors.YELLOW}Waiting for VCF Installer UI to be ready...{Colors.NC}")
        print(f"{Colors.BLUE}URL: {url}{Colors.NC}")
        print(f"{Colors.BLUE}Timeout: {timeout}s ({timeout // 60} minutes){Colors.NC}\n")

        while elapsed < timeout:
            try:
                response = requests.get(url, verify=False, timeout=5)
                if response.status_code == 200:
                    print(f"{Colors.GREEN}✓ VCF Installer UI is ready!{Colors.NC}\n")
                    return True
            except Exception:
                pass

            print(f"{Colors.YELLOW}⏳ VCF Installer UI not ready yet. "
                  f"Sleeping for {interval // 60} minutes... "
                  f"(elapsed: {elapsed // 60}/{timeout // 60} min){Colors.NC}")
            time.sleep(interval)
            elapsed += interval

        print(f"{Colors.RED}ERROR: Timeout waiting for VCF Installer UI{Colors.NC}")
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
                if vm.name == self.vcf_installer['vm_name']:
                    self.vm = vm
                    print(f"{Colors.GREEN}✓ Found VCF Installer VM: {vm.name}{Colors.NC}\n")
                    return True

            print(f"{Colors.RED}ERROR: VM not found: {self.vcf_installer['vm_name']}{Colors.NC}")
            return False

        except Exception as e:
            print(f"{Colors.RED}ERROR: Failed to find VM: {e}{Colors.NC}")
            return False

    def generate_config_script(self) -> str:
        """Generate bash script for VCF Installer configuration"""
        vcf = self.vcf_installer
        common = self.common

        script = "#!/bin/bash\n"
        script += "# Generated by VCF 9 Lab in a Box Script\n\n"

        # SSH keys if provided
        if common['ssh_root_key']:
            script += f"echo '{common['ssh_root_key']}' > /root/.ssh/authorized_keys\n"
            script += "sed -i 's/^PermitRootLogin.*/PermitRootLogin yes/g' /etc/ssh/sshd_config\n"
            script += "systemctl restart sshd\n"

        # Domain manager properties
        vcf_domain_config_file = "/etc/vmware/vcf/domainmanager/application.properties"
        if vcf.get('features', {}).get('skip_nic_speed_validation', False):
            script += f"echo 'enable.speed.of.physical.nics.validation=false' >> {vcf_domain_config_file}\n"

        # Feature properties
        vcf_feature_config_file = "/home/vcf/feature.properties"
        if vcf.get('features', {}).get('single_host_domain', False):
            script += f"echo 'feature.vcf.internal.single.host.domain=true' >> {vcf_feature_config_file}\n"
        script += f"chmod 755 {vcf_feature_config_file}\n"

        # Software depot configuration
        depot = vcf.get('depot', {})
        if depot.get('type') == 'offline':
            vcf_lcm_config_file = "/opt/vmware/vcf/lcm/lcm-app/conf/application-prod.properties"
            if not depot.get('use_https', True):
                script += f"sed -i -e '/lcm.depot.adapter.port=.*/a lcm.depot.adapter.httpsEnabled=false' {vcf_lcm_config_file}\n"

        # Restart services
        script += "echo 'y' | /opt/vmware/vcf/operationsmanager/scripts/cli/sddcmanager_restart_services.sh\n"

        return script

    def execute_guest_script(self, script_content: str, dry_run: bool = False) -> bool:
        """Execute script in VCF Installer VM guest"""
        if dry_run:
            print(f"{Colors.YELLOW}DRY RUN: Would execute the following script:{Colors.NC}\n")
            print(f"{Colors.BLUE}{script_content}{Colors.NC}\n")
            return True

        try:
            # Create credentials for guest operations
            creds = vim.vm.guest.NamePasswordAuthentication(
                username='root',
                password=self.vcf_installer['root_password']
            )

            # Get guest operations manager
            content = self.si.RetrieveContent()
            guest_ops_manager = content.guestOperationsManager
            file_manager = guest_ops_manager.fileManager
            process_manager = guest_ops_manager.processManager

            # Create temp script file in guest
            script_path = "/tmp/vcf_config.sh"

            print(f"{Colors.YELLOW}Transferring configuration script to VCF Installer VM...{Colors.NC}")

            # Write script content to guest
            file_attributes = vim.vm.guest.FileManager.FileAttributes()
            url = file_manager.InitiateFileTransferToGuest(
                vm=self.vm,
                auth=creds,
                guestFilePath=script_path,
                fileAttributes=file_attributes,
                fileSize=len(script_content),
                overwrite=True
            )

            # Upload the script
            response = requests.put(url, data=script_content, verify=False)
            if response.status_code not in [200, 201]:
                print(f"{Colors.RED}ERROR: Failed to upload script (HTTP {response.status_code}){Colors.NC}")
                return False

            print(f"{Colors.GREEN}✓ Script transferred successfully{Colors.NC}\n")

            # Execute the script
            print(f"{Colors.YELLOW}Executing configuration script on VCF Installer VM...{Colors.NC}")
            print(f"{Colors.YELLOW}This may take 5-10 minutes to restart all services...{Colors.NC}\n")

            program_spec = vim.vm.guest.ProcessManager.ProgramSpec(
                programPath='/bin/bash',
                arguments=script_path
            )

            pid = process_manager.StartProgramInGuest(
                vm=self.vm,
                auth=creds,
                spec=program_spec
            )

            # Wait for process to complete (poll every 30 seconds)
            print(f"{Colors.BLUE}Process ID: {pid}{Colors.NC}")
            print(f"{Colors.YELLOW}Waiting for process to complete...{Colors.NC}\n")

            max_wait = 600  # 10 minutes
            interval = 30
            elapsed = 0

            while elapsed < max_wait:
                processes = process_manager.ListProcessesInGuest(
                    vm=self.vm,
                    auth=creds,
                    pids=[pid]
                )

                if processes and len(processes) > 0:
                    process = processes[0]
                    if process.endTime:
                        if process.exitCode == 0:
                            print(f"{Colors.GREEN}✓ Configuration script completed successfully{Colors.NC}\n")
                            return True
                        else:
                            print(f"{Colors.RED}ERROR: Script exited with code {process.exitCode}{Colors.NC}")
                            return False

                time.sleep(interval)
                elapsed += interval
                print(f"{Colors.YELLOW}⏳ Still running... ({elapsed}s){Colors.NC}")

            print(f"{Colors.YELLOW}⚠ Script still running after {max_wait}s, continuing...{Colors.NC}\n")
            return True

        except Exception as e:
            print(f"{Colors.RED}ERROR: Failed to execute guest script: {e}{Colors.NC}")
            return False

    def disconnect(self):
        """Disconnect from ESXi"""
        if self.si:
            try:
                Disconnect(self.si)
                print(f"{Colors.GREEN}✓ Disconnected from ESXi host{Colors.NC}\n")
            except Exception:
                pass

    def configure(self, dry_run: bool = False) -> bool:
        """Configure VCF Installer"""
        print(f"{Colors.GREEN}========================================{Colors.NC}")
        print(f"{Colors.GREEN}VCF Installer Configuration{Colors.NC}")
        print(f"{Colors.GREEN}========================================{Colors.NC}\n")

        if dry_run:
            print(f"{Colors.YELLOW}DRY RUN MODE - No changes will be made{Colors.NC}\n")

        print(f"{Colors.BLUE}Configuration:{Colors.NC}")
        print(f"  VM Name:     {self.vcf_installer['vm_name']}")
        print(f"  Hostname:    {self.vcf_installer['hostname']}")
        print(f"  Target Host: {self.target_host['hostname']}")
        print()

        # Connect to ESXi
        if not self.connect_to_esxi():
            return False

        # Wait for VCF Installer UI
        if not self.wait_for_vcf_installer_ui():
            self.disconnect()
            return False

        # Find VM
        if not self.find_vm():
            self.disconnect()
            return False

        # Generate config script
        script_content = self.generate_config_script()

        # Execute script
        success = self.execute_guest_script(script_content, dry_run)

        # Disconnect
        self.disconnect()

        if success:
            print(f"{Colors.GREEN}========================================{Colors.NC}")
            print(f"{Colors.GREEN}Configuration Complete!{Colors.NC}")
            print(f"{Colors.GREEN}========================================{Colors.NC}\n")

            print(f"{Colors.BLUE}Next Steps:{Colors.NC}")
            print(f"  1. Access VCF Installer UI: https://{self.vcf_installer['hostname']}/")
            print(f"  2. Connect to offline depot (if using offline depot)")
            print(f"  3. Upload VCF deployment manifest JSON")
            print(f"  4. Start VCF deployment")
            print()

        return success


def main():
    parser = argparse.ArgumentParser(
        description="Configure VCF Installer post-deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Configure VCF Installer
  %(prog)s --dry-run                # Preview configuration without executing
  %(prog)s --config custom.yaml    # Use custom config file

Requirements:
  - VCF Installer VM must be deployed and powered on
  - ESXi host must be accessible
  - VMware Tools must be running in VCF Installer VM
        """
    )

    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Preview configuration without executing"
    )

    parser.add_argument(
        "-c", "--config",
        type=Path,
        help="Path to YAML config file (default: config/vcf-config.yaml)"
    )

    args = parser.parse_args()

    # Determine directories
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent

    # Determine config file
    config_file = args.config if args.config else project_dir / "config" / "vcf-config.yaml"

    # Load configuration
    config = load_config(config_file)

    # Print header
    print(f"{Colors.GREEN}========================================{Colors.NC}")
    print(f"{Colors.GREEN}VCF Installer Configuration Tool{Colors.NC}")
    print(f"{Colors.GREEN}========================================{Colors.NC}\n")

    # Create configurator
    configurator = VCFInstallerConfigurator(config)

    # Configure
    success = configurator.configure(dry_run=args.dry_run)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
