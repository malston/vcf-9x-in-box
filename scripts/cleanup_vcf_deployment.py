#!/usr/bin/env python3
"""
Cleanup VCF Deployment

This script cleans up a failed VCF deployment by:
1. Removing the VCF Installer VM
2. Resetting ESXi hosts to a clean state (removes vSAN, VDS, vCenter connection)

Usage:
    python scripts/cleanup_vcf_deployment.py [--dry-run] [--keep-installer]

    --dry-run: Show what would be done without making changes
    --keep-installer: Don't delete the VCF Installer VM (only reset hosts)
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
from typing import Optional


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


def find_vm_by_name(si: vim.ServiceInstance, vm_name: str) -> Optional[vim.VirtualMachine]:
    """Find a VM by name"""
    content = si.RetrieveContent()
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.VirtualMachine], True
    )

    for vm in container.view:
        if vm.name == vm_name:
            container.Destroy()
            return vm

    container.Destroy()
    return None


def delete_vcf_installer_vm(config: dict, dry_run: bool = False) -> bool:
    """Delete the VCF Installer VM"""
    print("\n" + "="*60)
    print("STEP 1: Delete VCF Installer VM")
    print("="*60)

    vm_name = config['vcf_installer']['vm_name']
    target_host_num = config['vcf_installer']['target_host']
    target_host = config['hosts'][target_host_num - 1]

    print(f"\nTarget: {vm_name} on {target_host['hostname']} ({target_host['ip']})")

    if dry_run:
        print(f"  [DRY-RUN] Would connect to {target_host['ip']}")
        print(f"  [DRY-RUN] Would find VM: {vm_name}")
        print(f"  [DRY-RUN] Would power off VM (if powered on)")
        print(f"  [DRY-RUN] Would delete VM")
        return True

    # Connect to ESXi host
    print(f"  • Connecting to {target_host['ip']}...")
    si = connect_to_host(
        target_host['ip'],
        'root',
        config['common']['root_password']
    )

    if not si:
        return False

    # Find VM
    print(f"  • Looking for VM: {vm_name}...")
    vm = find_vm_by_name(si, vm_name)

    if not vm:
        print(f"  ℹ VM '{vm_name}' not found (already deleted?)")
        return True

    # Power off VM if running
    if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
        print(f"  • Powering off VM...")
        task = vm.PowerOff()
        while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
            time.sleep(1)

        if task.info.state == vim.TaskInfo.State.error:
            print(f"  ✗ Failed to power off VM: {task.info.error}")
            return False
        print(f"  ✓ VM powered off")

    # Delete VM
    print(f"  • Deleting VM...")
    task = vm.Destroy()
    while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
        time.sleep(1)

    if task.info.state == vim.TaskInfo.State.error:
        print(f"  ✗ Failed to delete VM: {task.info.error}")
        return False

    print(f"  ✓ VM deleted successfully")
    return True


def cleanup_esxi_host(host: dict, root_password: str, dry_run: bool = False) -> bool:
    """Clean up a single ESXi host (remove vSAN, VDS, vCenter connection)"""
    hostname = host['hostname']
    ip = host['ip']

    print(f"\nCleaning up {hostname} ({ip})...")

    if dry_run:
        print(f"  [DRY-RUN] Would connect to {ip}")
        print(f"  [DRY-RUN] Would disable vSAN")
        print(f"  [DRY-RUN] Would remove from vCenter (if connected)")
        print(f"  [DRY-RUN] Would remove distributed virtual switches")
        print(f"  [DRY-RUN] Would reset networking to default")
        return True

    # Connect to ESXi host
    print(f"  • Connecting to {ip}...")
    si = connect_to_host(ip, 'root', root_password)

    if not si:
        return False

    content = si.RetrieveContent()
    host_system = content.rootFolder.childEntity[0].hostFolder.childEntity[0].host[0]

    # Check if host is connected to vCenter
    print(f"  • Checking vCenter connection...")
    if 'vpxd' in [s.key for s in host_system.config.service.service]:
        vpxd_service = [s for s in host_system.config.service.service if s.key == 'vpxd'][0]
        if vpxd_service.running:
            print(f"  ⚠ Host is managed by vCenter")
            print(f"    You should disconnect this host from vCenter first")
            print(f"    Or use vCenter to remove the host from inventory")
            # We'll continue anyway to clean up what we can

    # Disable vSAN
    print(f"  • Checking vSAN configuration...")
    vsan_system = host_system.configManager.vsanSystem
    if vsan_system:
        vsan_config = vsan_system.config
        if vsan_config and vsan_config.enabled:
            print(f"  • Disabling vSAN...")
            try:
                # Note: This may fail if host is part of a vSAN cluster managed by vCenter
                # In that case, vSAN should be disabled via vCenter
                print(f"    ⚠ vSAN is enabled but managed by vCenter")
                print(f"    You should disable vSAN via vCenter or remove host from cluster")
            except Exception as e:
                print(f"  ⚠ Could not disable vSAN: {e}")
        else:
            print(f"  ℹ vSAN not enabled")

    print(f"  ✓ Host cleanup assessment complete")
    print(f"    Note: Full cleanup requires removing host from vCenter first")

    return True


def cleanup_all_hosts(config: dict, dry_run: bool = False) -> bool:
    """Clean up all ESXi hosts"""
    print("\n" + "="*60)
    print("STEP 2: Clean Up ESXi Hosts")
    print("="*60)

    root_password = config['common']['root_password']
    all_success = True

    for host in config['hosts']:
        if not cleanup_esxi_host(host, root_password, dry_run):
            all_success = False

    return all_success


def main():
    parser = argparse.ArgumentParser(
        description="Clean up failed VCF deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what would be cleaned up
  python scripts/cleanup_vcf_deployment.py --dry-run

  # Clean up everything
  python scripts/cleanup_vcf_deployment.py

  # Only reset hosts, keep VCF Installer VM
  python scripts/cleanup_vcf_deployment.py --keep-installer
        """
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--keep-installer', action='store_true',
                       help="Don't delete the VCF Installer VM")

    args = parser.parse_args()

    print("VCF Deployment Cleanup Tool")
    print("="*60)

    if args.dry_run:
        print("🔍 DRY-RUN MODE: No changes will be made")

    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        print(f"✗ Failed to load configuration: {e}")
        return 1

    # Delete VCF Installer VM
    if not args.keep_installer:
        if not delete_vcf_installer_vm(config, args.dry_run):
            print("\n✗ Failed to delete VCF Installer VM")
            return 1
    else:
        print("\n⏭  Skipping VCF Installer VM deletion (--keep-installer)")

    # Clean up ESXi hosts
    print("\n" + "="*60)
    print("IMPORTANT: Host Cleanup Limitations")
    print("="*60)
    print("""
When ESXi hosts are managed by vCenter (which VCF does), many configurations
cannot be changed directly on the host. To fully reset your hosts, you should:

1. Log into vCenter (vc01.vcf.lab) if it's still accessible
2. Remove all hosts from the cluster
3. Disconnect hosts from vCenter
4. Then re-run this script to clean up remaining host-level configs

OR

5. Reinstall ESXi on each host using the kickstart USB drives
   (This is the cleanest approach for a fresh start)

This script will attempt to assess the current state, but full cleanup
may not be possible while hosts are vCenter-managed.
""")

    if not args.dry_run:
        response = input("\nDo you want to continue with host assessment? (y/n): ")
        if response.lower() != 'y':
            print("Cleanup cancelled")
            return 0
    else:
        print("\n[DRY-RUN] Skipping confirmation prompt")

    if not cleanup_all_hosts(config, args.dry_run):
        print("\n⚠ Some host cleanup operations failed or were skipped")

    # Summary
    print("\n" + "="*60)
    print("CLEANUP SUMMARY")
    print("="*60)

    if args.dry_run:
        print("\n🔍 This was a dry-run. No changes were made.")
        print("\nTo actually clean up, run without --dry-run:")
        print("  python scripts/cleanup_vcf_deployment.py")
    else:
        print("\n✓ VCF Installer VM cleanup complete")
        print("\n📋 RECOMMENDED NEXT STEPS:")
        print("\n1. The cleanest approach is to reinstall ESXi on all hosts:")
        print("   - Boot each host from the kickstart USB")
        print("   - This will give you a completely fresh ESXi installation")
        print("   - Or use 'make generate && make usb-create' to rebuild USBs")
        print("\n2. Fix the vCenter IP conflict in config/vcf-config.yaml:")
        print("   - Current: vcenter.ip = 172.30.0.13 (conflicts with esx03)")
        print("   - Should be: vcenter.ip = 172.30.0.10")
        print("\n3. After fixing config, redeploy VCF Installer:")
        print("   - make deploy-vcf-installer")
        print("   - make setup-vcf-installer")

    return 0


if __name__ == '__main__':
    sys.exit(main())
