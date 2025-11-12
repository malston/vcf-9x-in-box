#!/usr/bin/env python3
"""
List all VMs on ESXi hosts

Lists all VMs on each ESXi host with their power state and location.
"""

import argparse
import sys
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


def list_vms_on_host(host: dict, root_password: str) -> list:
    """List all VMs on a single ESXi host"""
    hostname = host['hostname']
    ip = host['ip']

    print(f"\n{'='*80}")
    print(f"Host: {hostname} ({ip})")
    print(f"{'='*80}")

    # Connect to ESXi host
    si = connect_to_host(ip, 'root', root_password)
    if not si:
        return []

    content = si.RetrieveContent()
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.VirtualMachine], True
    )

    vms = []
    for vm in container.view:
        vm_info = {
            'name': vm.name,
            'power_state': vm.runtime.powerState,
            'vmx_path': vm.config.files.vmPathName if vm.config else 'Unknown',
            'guest_os': vm.config.guestFullName if vm.config else 'Unknown',
            'vm_obj': vm
        }
        vms.append(vm_info)

        # Print VM details
        power_icon = "🟢" if vm_info['power_state'] == "poweredOn" else "⚫"
        print(f"  {power_icon} {vm_info['name']}")
        print(f"     Power: {vm_info['power_state']}")
        print(f"     OS: {vm_info['guest_os']}")
        print(f"     Path: {vm_info['vmx_path']}")

    container.Destroy()

    if not vms:
        print("  (No VMs found)")

    return vms


def main():
    parser = argparse.ArgumentParser(description="List all VMs on ESXi hosts")
    parser.add_argument('--config', help='Path to config file',
                       default='config/vcf-config.yaml')
    args = parser.parse_args()

    print("VM Inventory Report")
    print("="*80)

    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        print(f"✗ Failed to load configuration: {e}")
        return 1

    root_password = config['common']['root_password']
    all_vms = {}

    # List VMs on each host
    for host in config['hosts']:
        vms = list_vms_on_host(host, root_password)
        all_vms[host['hostname']] = vms

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")

    total_vms = sum(len(vms) for vms in all_vms.values())
    print(f"\nTotal VMs across all hosts: {total_vms}")

    for hostname, vms in all_vms.items():
        print(f"  {hostname}: {len(vms)} VMs")

    return 0


if __name__ == '__main__':
    sys.exit(main())
