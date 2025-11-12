#!/usr/bin/env python3
"""
Fix vSAN HCL Timestamp for VCF 9.0.1
Based on William Lam's workaround: https://williamlam.com/2025/06/vsan-esa-disk-hcl-workaround-for-vcf-9-0.html
"""
import argparse
import sys
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


def fix_vsan_hcl_timestamp(config, dry_run=False):
    """Fix vSAN HCL timestamp on VCF Installer VM"""
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
    print(f"{Colors.GREEN}vSAN HCL Timestamp Fix for VCF 9.0.1{Colors.NC}")
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

    # Check if HCL file exists
    print(f"{Colors.YELLOW}Checking vSAN HCL file...{Colors.NC}")
    hcl_file = "/nfs/vmware/vcf/nfs-mount/vsan-hcl/all.json"

    check_cmd = f'test -f {hcl_file} && echo "exists" || echo "not found"'
    spec = vim.vm.guest.ProcessManager.ProgramSpec(
        programPath='/bin/bash',
        arguments=f'-c "{check_cmd}"'
    )

    pid = process_manager.StartProgramInGuest(vm=vm, auth=creds, spec=spec)

    # Wait for command to complete
    import time
    for _ in range(10):
        processes = process_manager.ListProcessesInGuest(vm=vm, auth=creds, pids=[pid])
        if processes and processes[0].endTime:
            if processes[0].exitCode != 0:
                print(f"{Colors.RED}✗ HCL file not found at {hcl_file}{Colors.NC}")
                Disconnect(si)
                return False
            break
        time.sleep(1)

    print(f"{Colors.GREEN}✓ HCL file exists{Colors.NC}\n")

    if dry_run:
        print(f"{Colors.YELLOW}Would update timestamp in {hcl_file}{Colors.NC}")
        Disconnect(si)
        return True

    # Apply the fix (William Lam's workaround)
    print(f"{Colors.YELLOW}Applying timestamp fix...{Colors.NC}")

    # Generate timestamp using Python
    import datetime
    import pytz

    pst = pytz.timezone('America/Los_Angeles')
    now = datetime.datetime.now(pst)
    new_timestamp = int(now.timestamp())
    new_json_time = now.strftime("%B %-d, %Y, %-I:%M %p PST")

    # Escape for sed - need to escape forward slashes and special chars
    new_json_time_escaped = new_json_time.replace('/', '\\/')

    # Step 1: Create backup
    print(f"  Creating backup...")
    spec = vim.vm.guest.ProcessManager.ProgramSpec(
        programPath='/bin/cp',
        arguments=f'{hcl_file} {hcl_file}.bak'
    )
    pid = process_manager.StartProgramInGuest(vm=vm, auth=creds, spec=spec)

    for _ in range(10):
        processes = process_manager.ListProcessesInGuest(vm=vm, auth=creds, pids=[pid])
        if processes and processes[0].endTime:
            if processes[0].exitCode != 0:
                print(f"{Colors.RED}✗ Backup failed{Colors.NC}")
                Disconnect(si)
                return False
            break
        time.sleep(1)

    print(f"  {Colors.GREEN}✓ Backup created{Colors.NC}")

    # Step 2: Update timestamp field
    print(f"  Updating timestamp field...")
    sed_cmd = f'/bin/sed -i -E s/\\"timestamp\\":[0-9]+/\\"timestamp\\":{new_timestamp}/ {hcl_file}'
    spec = vim.vm.guest.ProcessManager.ProgramSpec(
        programPath='/bin/bash',
        arguments=f'-c "{sed_cmd}"'
    )
    pid = process_manager.StartProgramInGuest(vm=vm, auth=creds, spec=spec)

    for _ in range(10):
        processes = process_manager.ListProcessesInGuest(vm=vm, auth=creds, pids=[pid])
        if processes and processes[0].endTime:
            if processes[0].exitCode != 0:
                print(f"{Colors.RED}✗ Timestamp update failed{Colors.NC}")
                Disconnect(si)
                return False
            break
        time.sleep(1)

    print(f"  {Colors.GREEN}✓ Timestamp updated{Colors.NC}")

    # Step 3: Update jsonUpdatedTime field (optional - just for human readability)
    print(f"  Updating jsonUpdatedTime field...")
    sed_cmd2 = f'/bin/sed -i -E s/\\"jsonUpdatedTime\\":\\"[^\\"]*/\\"jsonUpdatedTime\\":\\"{new_json_time_escaped}/ {hcl_file}'
    spec = vim.vm.guest.ProcessManager.ProgramSpec(
        programPath='/bin/bash',
        arguments=f'-c "{sed_cmd2}"'
    )
    pid = process_manager.StartProgramInGuest(vm=vm, auth=creds, spec=spec)

    json_time_updated = False
    for _ in range(10):
        processes = process_manager.ListProcessesInGuest(vm=vm, auth=creds, pids=[pid])
        if processes and processes[0].endTime:
            if processes[0].exitCode == 0:
                json_time_updated = True
            break
        time.sleep(1)

    if json_time_updated:
        print(f"  {Colors.GREEN}✓ jsonUpdatedTime updated{Colors.NC}\n")
    else:
        print(f"  {Colors.YELLOW}⚠ jsonUpdatedTime update failed (non-critical){Colors.NC}\n")

    Disconnect(si)

    print(f"{Colors.GREEN}========================================{Colors.NC}")
    print(f"{Colors.GREEN}Fix Applied Successfully!{Colors.NC}")
    print(f"{Colors.GREEN}========================================{Colors.NC}\n")

    print(f"{Colors.BLUE}Next Steps:{Colors.NC}")
    print("  1. Return to VCF Installer UI")
    print("  2. Re-run validation")
    print("  3. HCL validation should now pass")
    print()

    return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Fix vSAN HCL timestamp for VCF 9.0.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                      # Apply the fix
  %(prog)s --dry-run            # Preview what would be done
  %(prog)s --config custom.yaml # Use custom config file

This script applies William Lam's workaround for VCF 9.0.1 vSAN HCL validation:
https://williamlam.com/2025/06/vsan-esa-disk-hcl-workaround-for-vcf-9-0.html

The fix updates the timestamp in /nfs/vmware/vcf/nfs-mount/vsan-hcl/all.json
to make it appear current (less than 90 days old).
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

    # Apply fix
    success = fix_vsan_hcl_timestamp(config, dry_run=args.dry_run)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
