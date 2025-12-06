#!/usr/bin/env python3
"""
ABOUTME: Power management for VCF 9.x management VMs to reclaim homelab capacity.
ABOUTME: Safely powers down optional management components when not actively managing VCF.

Usage:
    vcf_management_power.py status              # Show current state of all management VMs
    vcf_management_power.py power-down [tier]   # Power down VMs in specified tier (tier2, tier3, or all)
    vcf_management_power.py power-up [tier]     # Power up VMs in specified tier (tier2, tier3, or all)
    vcf_management_power.py validate            # Run pre-flight checks before power operations
    vcf_management_power.py audit              # Show capacity that can be reclaimed

Examples:
    # Check current status
    vcf_management_power.py status

    # Power down all unused Tier 3 VMs
    vcf_management_power.py power-down tier3

    # Power down all management VMs (Tier 2 + Tier 3)
    vcf_management_power.py power-down all

    # Bring everything back online
    vcf_management_power.py power-up all

    # Dry-run mode (show what would happen without making changes)
    vcf_management_power.py --dry-run power-down tier3
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pyVim import connect
from pyVmomi import vim


class VCFManagementPower:
    """Manage power state of VCF management VMs for capacity optimization."""

    def __init__(self, config_path: str, dry_run: bool = False):
        """Initialize with configuration file path."""
        self.config_path = Path(config_path)
        self.dry_run = dry_run
        self.config = self._load_config()
        self.si: Optional[vim.ServiceInstance] = None

    def _load_config(self) -> Dict:
        """Load tier configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Expected location: config/vcf-management-tiers.yaml"
            )

        with open(self.config_path) as f:
            return yaml.safe_load(f)

    def _get_vcenter_password(self) -> str:
        """Get vCenter password from environment variable or prompt."""
        password = os.environ.get("VCF_VCENTER_PASSWORD")
        if not password:
            raise ValueError(
                "vCenter password not provided.\n"
                "Set environment variable: export VCF_VCENTER_PASSWORD='your-password'\n"
                "Or run: read -s VCF_VCENTER_PASSWORD && export VCF_VCENTER_PASSWORD"
            )
        return password

    def connect_vcenter(self) -> None:
        """Connect to vCenter Server."""
        vcenter_config = self.config["vcenter"]
        password = self._get_vcenter_password()

        print(f"Connecting to vCenter: {vcenter_config['hostname']}")

        try:
            self.si = connect.SmartConnect(
                host=vcenter_config["hostname"],
                user=vcenter_config["username"],
                pwd=password,
                disableSslCertValidation=True,  # Homelab with self-signed certs
            )
            print("✓ Connected to vCenter successfully\n")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to vCenter: {e}")

    def disconnect_vcenter(self) -> None:
        """Disconnect from vCenter Server."""
        if self.si:
            connect.Disconnect(self.si)
            self.si = None

    def _get_vm_by_name(self, vm_name: str) -> Optional[vim.VirtualMachine]:
        """Find a VM by name in vCenter inventory."""
        if not self.si:
            raise RuntimeError("Not connected to vCenter")

        content = self.si.RetrieveContent()
        container = content.rootFolder
        view_type = [vim.VirtualMachine]
        recursive = True

        container_view = content.viewManager.CreateContainerView(
            container, view_type, recursive
        )

        vms = container_view.view
        container_view.Destroy()

        for vm in vms:
            if vm.name == vm_name:
                return vm

        return None

    def get_vm_status(self, vm_name: str) -> Dict:
        """Get detailed status of a VM."""
        vm = self._get_vm_by_name(vm_name)

        if not vm:
            return {
                "name": vm_name,
                "exists": False,
                "power_state": "NOT_FOUND",
                "cpu": None,
                "memory_gb": None,
            }

        # Get configuration details
        config = vm.summary.config
        runtime = vm.summary.runtime

        return {
            "name": vm_name,
            "exists": True,
            "power_state": str(runtime.powerState),
            "cpu": config.numCpu,
            "memory_gb": round(config.memorySizeMB / 1024, 1),
            "guest_tools": str(vm.guest.toolsRunningStatus),
            "hostname": config.name,
        }

    def show_status(self, tier_filter: Optional[str] = None) -> None:
        """Display current status of all management VMs."""
        print("=" * 80)
        print("VCF Management VM Status Report")
        print("=" * 80)

        tiers = self.config["tiers"]
        tier_keys = [tier_filter] if tier_filter else list(tiers.keys())

        for tier_key in tier_keys:
            if tier_key not in tiers:
                print(f"Warning: Unknown tier '{tier_key}', skipping")
                continue

            tier = tiers[tier_key]
            print(f"\n{tier['name']} ({tier_key.upper()})")
            print("-" * 80)
            print(f"Description: {tier['description']}")
            print(f"Power Management Enabled: {tier.get('power_management', False)}")
            print()

            print(
                f"{'VM':<20} {'Hostname':<25} {'State':<15} {'CPU':>5} {'RAM':>8}"
            )
            print("-" * 80)

            total_cpu = 0
            total_ram = 0
            powered_on_count = 0

            for vm_config in tier["vms"]:
                vm_name = vm_config["name"]
                status = self.get_vm_status(vm_name)

                if not status["exists"]:
                    if vm_config.get("optional", False):
                        # Optional VM not found - this is OK
                        print(
                            f"{vm_name:<20} {'(optional)':<25} {'NOT_DEPLOYED':<15} {'-':>5} {'-':>8}"
                        )
                    else:
                        # Required VM not found - this is a problem
                        print(
                            f"{vm_name:<20} {vm_config['hostname']:<25} {'NOT_FOUND':<15} {'-':>5} {'-':>8}"
                        )
                    continue

                state_display = (
                    "POWERED_ON"
                    if status["power_state"] == "poweredOn"
                    else "POWERED_OFF"
                )
                cpu_display = f"{status['cpu']}" if status["cpu"] else "-"
                ram_display = (
                    f"{status['memory_gb']}GB" if status["memory_gb"] else "-"
                )

                print(
                    f"{vm_name:<20} {vm_config['hostname']:<25} {state_display:<15} {cpu_display:>5} {ram_display:>8}"
                )

                if status["power_state"] == "poweredOn":
                    powered_on_count += 1
                    if status["cpu"]:
                        total_cpu += status["cpu"]
                    if status["memory_gb"]:
                        total_ram += status["memory_gb"]

            print("-" * 80)
            print(
                f"{'TIER TOTAL':<20} {f'({powered_on_count} powered on)':<25} {'':<15} {total_cpu:>5} {total_ram:>6.1f}GB"
            )
            print()

    def power_down_tier(self, tier_name: str) -> None:
        """Power down all VMs in specified tier."""
        if tier_name not in self.config["tiers"]:
            raise ValueError(f"Unknown tier: {tier_name}")

        tier = self.config["tiers"][tier_name]

        if not tier.get("power_management", False):
            print(f"\nWARNING: {tier['name']} does not allow power management!")
            print("These VMs are critical infrastructure and should remain powered on.")
            response = input("Are you ABSOLUTELY SURE you want to proceed? (yes/NO): ")
            if response.lower() != "yes":
                print("Aborted.")
                return

        print(f"\nPowering down {tier['name']} VMs...")
        print("=" * 80)

        for vm_config in tier["vms"]:
            vm_name = vm_config["name"]
            display_name = vm_config["display_name"]

            status = self.get_vm_status(vm_name)

            if not status["exists"]:
                if vm_config.get("optional", False):
                    print(f"⊘ {display_name} ({vm_name}) - Not deployed, skipping")
                else:
                    print(f"⚠ {display_name} ({vm_name}) - NOT FOUND!")
                continue

            if status["power_state"] == "poweredOff":
                print(f"○ {display_name} ({vm_name}) - Already powered off")
                continue

            print(f"● {display_name} ({vm_name}) - Shutting down gracefully...")

            if self.dry_run:
                print(f"  [DRY-RUN] Would execute: shutdown guest OS, then power off")
                continue

            vm = self._get_vm_by_name(vm_name)
            if not vm:
                continue

            # Try graceful shutdown first (requires VMware Tools)
            try:
                vm.ShutdownGuest()
                print("  Waiting for graceful shutdown (max 5 minutes)...")

                # Wait up to 5 minutes for graceful shutdown (large VMs like vRA need time)
                for i in range(60):  # 60 * 5 seconds = 300 seconds
                    time.sleep(5)
                    vm_status = self.get_vm_status(vm_name)
                    if vm_status["power_state"] == "poweredOff":
                        print(f"  ✓ Graceful shutdown completed")
                        break
                else:
                    # Timeout - force power off
                    print(
                        "  ⚠ Graceful shutdown timeout, forcing power off..."
                    )
                    task = vm.PowerOff()
                    self._wait_for_task(task)
                    print(f"  ✓ Forced power off completed")

            except Exception as e:
                # VMware Tools not available or other error - force power off
                print(
                    f"  ⚠ Graceful shutdown failed ({e}), forcing power off..."
                )
                try:
                    task = vm.PowerOff()
                    self._wait_for_task(task)
                    print(f"  ✓ Forced power off completed")
                except Exception as e2:
                    print(f"  ✗ Power off failed: {e2}")

        print("\n✓ Power down operation completed")

    def power_up_tier(self, tier_name: str) -> None:
        """Power up all VMs in specified tier."""
        if tier_name not in self.config["tiers"]:
            raise ValueError(f"Unknown tier: {tier_name}")

        tier = self.config["tiers"][tier_name]

        print(f"\nPowering up {tier['name']} VMs...")
        print("=" * 80)

        for vm_config in tier["vms"]:
            vm_name = vm_config["name"]
            display_name = vm_config["display_name"]

            status = self.get_vm_status(vm_name)

            if not status["exists"]:
                if vm_config.get("optional", False):
                    print(f"⊘ {display_name} ({vm_name}) - Not deployed, skipping")
                else:
                    print(f"⚠ {display_name} ({vm_name}) - NOT FOUND!")
                continue

            if status["power_state"] == "poweredOn":
                print(f"● {display_name} ({vm_name}) - Already powered on")
                continue

            print(f"○ {display_name} ({vm_name}) - Powering on...")

            if self.dry_run:
                print(f"  [DRY-RUN] Would execute: power on VM")
                continue

            vm = self._get_vm_by_name(vm_name)
            if not vm:
                continue

            try:
                task = vm.PowerOn()
                self._wait_for_task(task)
                print(f"  ✓ Powered on successfully")

                # Wait a bit for VMware Tools to start
                print("  Waiting for VMware Tools...")
                for i in range(12):  # Wait up to 60 seconds
                    time.sleep(5)
                    vm_status = self.get_vm_status(vm_name)
                    if "toolsRunning" in vm_status.get("guest_tools", ""):
                        print(f"  ✓ VMware Tools running")
                        break
                else:
                    print("  ⚠ VMware Tools timeout (may still be starting)")

            except Exception as e:
                print(f"  ✗ Power on failed: {e}")

        print("\n✓ Power up operation completed")

    def _wait_for_task(self, task: vim.Task, timeout: int = 300) -> None:
        """Wait for a vCenter task to complete."""
        start_time = time.time()

        while task.info.state in [vim.TaskInfo.State.running, vim.TaskInfo.State.queued]:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Task timeout after {timeout} seconds")
            time.sleep(1)

        if task.info.state != vim.TaskInfo.State.success:
            raise RuntimeError(f"Task failed: {task.info.error}")

    def validate_environment(self) -> bool:
        """Run pre-flight checks before power operations."""
        print("\nValidating VCF environment before power operations...")
        print("=" * 80)

        all_ok = True

        # Check 1: vCenter connectivity
        print("\n1. vCenter Connectivity")
        try:
            if not self.si:
                self.connect_vcenter()
            print("   ✓ vCenter connection successful")
        except Exception as e:
            print(f"   ✗ vCenter connection failed: {e}")
            all_ok = False

        # Check 2: Verify Tier 1 VMs are running
        print("\n2. Critical Infrastructure (Tier 1) Status")
        tier1 = self.config["tiers"]["tier1"]
        for vm_config in tier1["vms"]:
            vm_name = vm_config["name"]
            status = self.get_vm_status(vm_name)

            if not status["exists"]:
                print(f"   ✗ {vm_config['display_name']} - NOT FOUND!")
                all_ok = False
            elif status["power_state"] != "poweredOn":
                print(f"   ✗ {vm_config['display_name']} - NOT RUNNING!")
                all_ok = False
            else:
                print(f"   ✓ {vm_config['display_name']} - Running")

        # Check 3: Verify no active VCF lifecycle operations
        print("\n3. VCF Lifecycle Operations")
        print("   ⚠ Unable to check automatically - manual verification required")
        print("   Please verify no active:")
        print("     - VCF updates/patches in progress")
        print("     - Host maintenance operations")
        print("     - Cluster expansions/contractions")

        print("\n" + "=" * 80)
        if all_ok:
            print("✓ Pre-flight validation PASSED")
            print("\nIt should be safe to proceed with power operations.")
        else:
            print("✗ Pre-flight validation FAILED")
            print("\nPlease resolve issues before proceeding with power operations.")

        return all_ok

    def show_capacity_audit(self) -> None:
        """Display capacity that can be reclaimed by powering down VMs."""
        print("\nVCF Management VM Capacity Audit")
        print("=" * 80)

        homelab = self.config["homelab"]
        print(f"\nPhysical Cluster Capacity: {homelab['total_physical_ram_gb']}GB RAM")
        print(
            f"Recommended Max Workload Allocation: {homelab['recommended_max_workload_allocation']}GB RAM"
        )

        print("\n" + "-" * 80)
        print("Capacity Reclaimable by Powering Down Optional VMs (Tier 3)")
        print("-" * 80)

        tier3 = self.config["tiers"]["tier3"]
        total_ram = 0
        total_cpu = 0

        print(
            f"{'VM':<20} {'Hostname':<25} {'Current State':<15} {'RAM':>8} {'CPU':>5}"
        )
        print("-" * 80)

        for vm_config in tier3["vms"]:
            vm_name = vm_config["name"]
            status = self.get_vm_status(vm_name)

            if not status["exists"]:
                if vm_config.get("optional", False):
                    continue  # Optional VM not deployed
                else:
                    print(
                        f"{vm_name:<20} {vm_config['hostname']:<25} {'NOT_FOUND':<15} {'-':>8} {'-':>5}"
                    )
                continue

            state = "ON" if status["power_state"] == "poweredOn" else "OFF"
            ram_gb = status["memory_gb"] or vm_config.get("estimated_ram_gb", 0)
            cpu = status["cpu"] or vm_config.get("estimated_vcpu", 0)

            if status["power_state"] == "poweredOn":
                total_ram += ram_gb
                total_cpu += cpu

            print(
                f"{vm_name:<20} {vm_config['hostname']:<25} {state:<15} {ram_gb:>6.1f}GB {cpu:>5}"
            )

        print("-" * 80)
        print(
            f"{'TOTAL RECLAIMABLE':<46} {'(if all powered off)':<15} {total_ram:>6.1f}GB {total_cpu:>5}"
        )

        percentage = (
            total_ram / homelab["total_physical_ram_gb"] * 100
            if total_ram > 0
            else 0
        )
        print(
            f"\nPowering down Tier 3 VMs would reclaim ~{percentage:.1f}% of cluster capacity"
        )

        # Show right-sizing recommendations
        print("\n" + "-" * 80)
        print("Right-Sizing Recommendations (for VMs you want to keep running)")
        print("-" * 80)

        for recommendation in homelab.get("right_sizing", []):
            vm_name = recommendation["vm"]
            current = recommendation["current_typical_allocation_gb"]
            recommended = recommendation["recommended_homelab_gb"]
            savings = current - recommended

            print(f"\n{vm_name}:")
            print(f"  Current typical allocation: {current}GB")
            print(f"  Recommended for homelab: {recommended}GB")
            print(f"  Potential savings: {savings}GB")
            print(f"  Notes: {recommendation['notes']}")

        print("\n" + "=" * 80)


def main():
    """Main entry point for VCF management power CLI."""
    parser = argparse.ArgumentParser(
        description="Manage power state of VCF 9.x management VMs for capacity optimization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "command",
        choices=["status", "power-down", "power-up", "validate", "audit"],
        help="Command to execute",
    )

    parser.add_argument(
        "tier",
        nargs="?",
        choices=["tier1", "tier2", "tier3", "all"],
        help="Tier to operate on (for power-down/power-up commands)",
    )

    parser.add_argument(
        "--config",
        default="config/vcf-management-tiers.yaml",
        help="Path to tier configuration file",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes",
    )

    args = parser.parse_args()

    # Validate tier argument for power commands
    if args.command in ["power-down", "power-up"] and not args.tier:
        parser.error(f"{args.command} command requires tier argument")

    # Create power manager instance
    try:
        manager = VCFManagementPower(args.config, dry_run=args.dry_run)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Execute command
    try:
        if args.command == "status":
            manager.connect_vcenter()
            manager.show_status(args.tier)

        elif args.command == "validate":
            manager.connect_vcenter()
            success = manager.validate_environment()
            sys.exit(0 if success else 1)

        elif args.command == "audit":
            manager.connect_vcenter()
            manager.show_capacity_audit()

        elif args.command == "power-down":
            manager.connect_vcenter()

            # Handle "all" tier
            if args.tier == "all":
                print("\nPowering down ALL management VMs (Tier 2 + Tier 3)")
                response = input(
                    "This will power down VCF Operations Console and monitoring. Continue? (yes/NO): "
                )
                if response.lower() != "yes":
                    print("Aborted.")
                    sys.exit(0)

                # Power down in reverse startup order
                manager.power_down_tier("tier3")
                manager.power_down_tier("tier2")
            else:
                manager.power_down_tier(args.tier)

        elif args.command == "power-up":
            manager.connect_vcenter()

            # Handle "all" tier
            if args.tier == "all":
                print("\nPowering up ALL management VMs (Tier 2 + Tier 3)")

                # Power up in startup order
                manager.power_up_tier("tier2")
                manager.power_up_tier("tier3")
            else:
                manager.power_up_tier(args.tier)

    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
    finally:
        if manager.si:
            manager.disconnect_vcenter()


if __name__ == "__main__":
    main()
