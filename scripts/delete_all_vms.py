#!/usr/bin/env python3
"""
Delete All VMs from ESXi Hosts

Deletes all VMs from ESXi hosts to prepare for fresh VCF deployment.

Usage:
    python scripts/delete_all_vms.py [--dry-run] [--exclude VM1,VM2]

    --dry-run: Show what would be deleted without making changes
    --exclude: Comma-separated list of VM names to skip (e.g., --exclude vm1,vm2)
"""

import argparse
import sys
import time
import yaml
from pathlib import Path
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import ssl
import atexit
from typing import Optional, List


def load_config() -> dict:
    """Load configuration from vcf-config.yaml"""
    config_path = Path(__file__).parent.parent / "config" / "vcf-config.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def connect_to_host(host_ip: str, username: str, password: str) -> Optional[vim.ServiceInstance]:
    """Connect to an ESXi host"""
    try:
        context = ssl._create_unverified_context()
        si = SmartConnect(
            host=host_ip,
            user=username,
            pwd=password,
            port=443,
            sslContext=context
        )
        atexit.register(Disconnect, si)
        return si
    except Exception as e:
        print(f"  ✗ Failed to connect to {host_ip}: {e}")
        return None


def delete_vms_on_host(host: dict, root_password: str, exclude_vms: List[str], dry_run: bool = False) -> bool:
    """Delete all VMs on a single ESXi host"""
    hostname = host['hostname']
    ip = host['ip']

    print(f"\n{'='*80}")
    print(f"Host: {hostname} ({ip})")
    print(f"{'='*80}")

    # Connect to ESXi host
    si = connect_to_host(ip, 'root', root_password)
    if not si:
        return False

    content = si.RetrieveContent()
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.VirtualMachine], True
    )

    vms_to_delete = []
    for vm in container.view:
        if vm.name not in exclude_vms:
            vms_to_delete.append(vm)

    container.Destroy()

    if not vms_to_delete:
        print("  ℹ No VMs to delete on this host")
        return True

    print(f"  Found {len(vms_to_delete)} VM(s) to delete:\n")

    success = True
    for vm in vms_to_delete:
        vm_name = vm.name
        power_state = vm.runtime.powerState
        vmx_path = vm.config.files.vmPathName if vm.config else 'Unknown'

        power_icon = "🟢" if power_state == "poweredOn" else "⚫"
        print(f"  {power_icon} {vm_name}")
        print(f"     Power: {power_state}")
        print(f"     Path: {vmx_path}")

        if dry_run:
            print(f"     [DRY-RUN] Would power off and delete this VM")
        else:
            # Power off if running
            if power_state == vim.VirtualMachinePowerState.poweredOn:
                print(f"     • Powering off...")
                try:
                    task = vm.PowerOff()
                    while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
                        time.sleep(0.5)

                    if task.info.state == vim.TaskInfo.State.error:
                        print(f"     ✗ Failed to power off: {task.info.error}")
                        success = False
                        continue
                    print(f"     ✓ Powered off")
                except Exception as e:
                    print(f"     ✗ Failed to power off: {e}")
                    success = False
                    continue

            # Delete VM
            print(f"     • Deleting VM...")
            try:
                task = vm.Destroy()
                while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
                    time.sleep(0.5)

                if task.info.state == vim.TaskInfo.State.error:
                    print(f"     ✗ Failed to delete: {task.info.error}")
                    success = False
                    continue
                print(f"     ✓ Deleted successfully")
            except Exception as e:
                print(f"     ✗ Failed to delete: {e}")
                success = False

        print()

    return success


def main():
    parser = argparse.ArgumentParser(
        description="Delete all VMs from ESXi hosts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what would be deleted
  python scripts/delete_all_vms.py --dry-run

  # Delete all VMs
  python scripts/delete_all_vms.py

  # Delete all VMs except specific ones
  python scripts/delete_all_vms.py --exclude vc01,test-vm
        """
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--exclude', type=str, default='',
                       help='Comma-separated list of VM names to skip')
    parser.add_argument('--config', help='Path to config file',
                       default='config/vcf-config.yaml')

    args = parser.parse_args()

    print("Delete All VMs Tool")
    print("="*80)

    if args.dry_run:
        print("🔍 DRY-RUN MODE: No changes will be made\n")

    # Parse excluded VMs
    exclude_vms = [vm.strip() for vm in args.exclude.split(',') if vm.strip()]
    if exclude_vms:
        print(f"ℹ Excluding VMs: {', '.join(exclude_vms)}\n")

    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        print(f"✗ Failed to load configuration: {e}")
        return 1

    root_password = config['common']['root_password']

    # Warning
    if not args.dry_run:
        print("\n" + "!"*80)
        print("WARNING: This will DELETE ALL VMs from all ESXi hosts!")
        print("!"*80)
        print("\nThis action cannot be undone. VMs will be:")
        print("  1. Powered off (if running)")
        print("  2. Deleted from inventory")
        print("  3. VM files removed from datastores")

        if exclude_vms:
            print(f"\nExcluding: {', '.join(exclude_vms)}")

        response = input("\nAre you sure you want to continue? (type 'yes' to confirm): ")
        if response.lower() != 'yes':
            print("\nOperation cancelled")
            return 0

    # Delete VMs on each host
    all_success = True
    for host in config['hosts']:
        if not delete_vms_on_host(host, root_password, exclude_vms, args.dry_run):
            all_success = False

    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)

    if args.dry_run:
        print("\n🔍 This was a dry-run. No VMs were deleted.")
        print("\nTo actually delete VMs, run without --dry-run:")
        print("  python scripts/delete_all_vms.py")
    elif all_success:
        print("\n✓ All VMs deleted successfully")
        print("\n📋 NEXT STEPS:")
        print("  1. Redeploy VCF Installer:")
        print("     make deploy-vcf-installer")
        print("  2. Configure VCF Installer:")
        print("     make setup-vcf-installer")
    else:
        print("\n⚠ Some VMs failed to delete")
        print("Check the errors above and try again, or manually delete the VMs")

    return 0 if all_success else 1


if __name__ == '__main__':
    sys.exit(main())
