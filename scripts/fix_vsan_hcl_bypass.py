#!/usr/bin/env python3
"""
Enable vSAN ESA HCL Bypass for VCF 9.0.1
Based on William Lam's article: https://williamlam.com/2025/09/enhancement-in-vcf-9-0-1-to-bypass-vsan-esa-hcl-host-commission-10gbe-nic-check.html
"""
import argparse
import sys
import time
from pathlib import Path

from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim

# Add scripts directory to path for vcf_secrets import
sys.path.insert(0, str(Path(__file__).parent))

# pylint: disable=wrong-import-position
from vcf_secrets import load_config_with_secrets


# Color output
class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


def enable_vsan_hcl_bypass(config, dry_run=False):
    """Enable vSAN ESA HCL bypass in VCF 9.0.1"""
    vcf_installer = config['vcf_installer']
    common = config['common']

    # Determine target host
    target_host_num = vcf_installer['target_host']
    target_host = None
    for host in config['hosts']:
        if host['number'] == target_host_num:
            target_host = host
            break

    if not target_host:
        print(f"{Colors.RED}ERROR: Target host {target_host_num} not found in config{Colors.NC}")
        return False

    print(f"{Colors.GREEN}========================================{Colors.NC}")
    print(f"{Colors.GREEN}vSAN ESA HCL Bypass (VCF 9.0.1){Colors.NC}")
    print(f"{Colors.GREEN}========================================{Colors.NC}\n")

    if dry_run:
        print(f"{Colors.YELLOW}DRY RUN MODE - No changes will be made{Colors.NC}\n")

    print(f"{Colors.BLUE}Target:{Colors.NC}")
    print(f"  VM: {vcf_installer['vm_name']}")
    print(f"  Host: {target_host['hostname']}\n")

    # Connect to ESXi
    print(f"{Colors.YELLOW}Connecting to ESXi host...{Colors.NC}")
    try:
        si = SmartConnect(
            host=target_host['ip'],
            user='root',
            pwd=common['root_password'],
            disableSslCertValidation=True
        )
        print(f"{Colors.GREEN}✓ Connected{Colors.NC}\n")
    except Exception as e:
        print(f"{Colors.RED}ERROR: Failed to connect: {e}{Colors.NC}")
        return False

    # Find VM
    print(f"{Colors.YELLOW}Finding VCF Installer VM...{Colors.NC}")
    vm = None
    try:
        content = si.RetrieveContent()
        container_view = content.viewManager.CreateContainerView(
            content.rootFolder, [vim.VirtualMachine], True
        )
        for v in container_view.view:
            if v.name == vcf_installer['vm_name']:
                vm = v
                break

        if not vm:
            print(f"{Colors.RED}ERROR: VM not found{Colors.NC}")
            Disconnect(si)
            return False

        print(f"{Colors.GREEN}✓ Found VM{Colors.NC}\n")
    except Exception as e:
        print(f"{Colors.RED}ERROR: {e}{Colors.NC}")
        Disconnect(si)
        return False

    # Create credentials for guest operations
    creds = vim.vm.guest.NamePasswordAuthentication(
        username='root',
        password=vcf_installer['root_password']
    )

    process_manager = si.content.guestOperationsManager.processManager

    config_file = "/etc/vmware/vcf/domainmanager/application-prod.properties"
    property_line = "vsan.esa.sddc.managed.disk.claim=true"

    if dry_run:
        print(f"{Colors.YELLOW}Would add to {config_file}:{Colors.NC}")
        print(f"  {property_line}\n")
        print(f"{Colors.YELLOW}Would restart domainmanager service{Colors.NC}\n")
        Disconnect(si)
        return True

    # Check if property already exists
    print(f"{Colors.YELLOW}Checking current configuration...{Colors.NC}")
    check_cmd = f'grep -q "{property_line}" {config_file}'
    spec = vim.vm.guest.ProcessManager.ProgramSpec(
        programPath='/bin/bash',
        arguments=f'-c "{check_cmd}"'
    )
    pid = process_manager.StartProgramInGuest(vm=vm, auth=creds, spec=spec)

    property_exists = False
    for _ in range(10):
        processes = process_manager.ListProcessesInGuest(vm=vm, auth=creds, pids=[pid])
        if processes and processes[0].endTime:
            # grep exit code 0 = found, 1 = not found
            if processes[0].exitCode == 0:
                property_exists = True
            break
        time.sleep(1)

    if property_exists:
        print(f"{Colors.YELLOW}  Property already configured{Colors.NC}\n")
        Disconnect(si)
        return True

    # Add property
    print(f"{Colors.YELLOW}Adding vSAN ESA HCL bypass property...{Colors.NC}")
    add_cmd = f'echo "{property_line}" >> {config_file}'
    spec = vim.vm.guest.ProcessManager.ProgramSpec(
        programPath='/bin/bash',
        arguments=f'-c "{add_cmd}"'
    )
    pid = process_manager.StartProgramInGuest(vm=vm, auth=creds, spec=spec)

    for _ in range(10):
        processes = process_manager.ListProcessesInGuest(vm=vm, auth=creds, pids=[pid])
        if processes and processes[0].endTime:
            if processes[0].exitCode != 0:
                print(f"{Colors.RED}✗ Failed to add property{Colors.NC}")
                Disconnect(si)
                return False
            break
        time.sleep(1)

    print(f"{Colors.GREEN}✓ Property added{Colors.NC}\n")

    # Restart domainmanager service
    print(f"{Colors.YELLOW}Restarting domainmanager service...{Colors.NC}")
    print(f"{Colors.BLUE}This may take 2-3 minutes...{Colors.NC}\n")

    restart_cmd = 'systemctl restart domainmanager'
    spec = vim.vm.guest.ProcessManager.ProgramSpec(
        programPath='/bin/bash',
        arguments=f'-c "{restart_cmd}"'
    )
    pid = process_manager.StartProgramInGuest(vm=vm, auth=creds, spec=spec)

    # Wait for restart to complete
    for _ in range(60):
        processes = process_manager.ListProcessesInGuest(vm=vm, auth=creds, pids=[pid])
        if processes and processes[0].endTime:
            if processes[0].exitCode != 0:
                print(f"{Colors.RED}✗ Service restart failed{Colors.NC}")
                Disconnect(si)
                return False
            break
        time.sleep(3)

    print(f"{Colors.GREEN}✓ Service restarted{Colors.NC}\n")

    Disconnect(si)

    print(f"{Colors.GREEN}========================================{Colors.NC}")
    print(f"{Colors.GREEN}vSAN ESA HCL Bypass Enabled!{Colors.NC}")
    print(f"{Colors.GREEN}========================================{Colors.NC}\n")

    print(f"{Colors.BLUE}Next Steps:{Colors.NC}")
    print("  1. Return to VCF Installer UI")
    print("  2. Re-run validation")
    print("  3. vSAN HCL validation should now pass")
    print()

    return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Enable vSAN ESA HCL bypass for VCF 9.0.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                      # Enable the bypass
  %(prog)s --dry-run            # Preview what would be done
  %(prog)s --config custom.yaml # Use custom config file

This script uses the VCF 9.0.1 built-in feature to bypass vSAN ESA HCL validation
by setting vsan.esa.sddc.managed.disk.claim=true in the domainmanager config.

Reference: https://williamlam.com/2025/09/enhancement-in-vcf-9-0-1-to-bypass-vsan-esa-hcl-host-commission-10gbe-nic-check.html
        """
    )

    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Preview changes without applying them"
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

    # Load configuration with secrets
    config = load_config_with_secrets(config_file)

    # Apply bypass
    success = enable_vsan_hcl_bypass(config, dry_run=args.dry_run)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
