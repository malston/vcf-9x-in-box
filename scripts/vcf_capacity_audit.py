#!/usr/bin/env python3
"""
ABOUTME: Detailed capacity audit for VCF 9.x management VMs.
ABOUTME: Analyzes actual resource usage vs allocation to identify right-sizing opportunities.

Usage:
    vcf_capacity_audit.py                        # Full audit report with cluster summary
    vcf_capacity_audit.py --cluster-summary-only # Quick cluster capacity check
    vcf_capacity_audit.py --vm-name vc01         # Audit specific VM
    vcf_capacity_audit.py --export-csv audit.csv # Export to CSV

Examples:
    # Run full audit with cluster capacity overview
    vcf_capacity_audit.py

    # Quick cluster capacity check (fast)
    vcf_capacity_audit.py --cluster-summary-only

    # Audit specific management VM
    vcf_capacity_audit.py --vm-name opsfm01

    # Export results for analysis
    vcf_capacity_audit.py --export-csv vcf-capacity-audit.csv
"""

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pyVim import connect
from pyVmomi import vim


class VCFCapacityAuditor:
    """Audit VCF management VM capacity usage and provide right-sizing recommendations."""

    def __init__(self, config_path: str):
        """Initialize with configuration file path."""
        self.config_path = Path(config_path)
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
        """Get vCenter password from environment variable."""
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
                disableSslCertValidation=True,
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

    def get_detailed_vm_stats(self, vm_name: str) -> Dict:
        """Get detailed resource statistics for a VM."""
        vm = self._get_vm_by_name(vm_name)

        if not vm:
            return {
                "name": vm_name,
                "exists": False,
            }

        # Get configuration
        config = vm.summary.config
        runtime = vm.summary.runtime
        quick_stats = vm.summary.quickStats

        # Calculate usage percentages
        cpu_usage_mhz = quick_stats.overallCpuUsage or 0
        memory_usage_mb = quick_stats.guestMemoryUsage or 0
        memory_active_mb = quick_stats.hostMemoryUsage or 0

        # Get allocated resources
        cpu_allocated = config.numCpu
        memory_allocated_mb = config.memorySizeMB

        # Calculate percentages
        memory_usage_percent = (
            (memory_usage_mb / memory_allocated_mb * 100)
            if memory_allocated_mb > 0
            else 0
        )
        memory_active_percent = (
            (memory_active_mb / memory_allocated_mb * 100)
            if memory_allocated_mb > 0
            else 0
        )

        # Get storage info
        storage_committed_gb = (
            round(vm.summary.storage.committed / (1024**3), 2)
            if vm.summary.storage
            else 0
        )
        storage_uncommitted_gb = (
            round(vm.summary.storage.uncommitted / (1024**3), 2)
            if vm.summary.storage
            else 0
        )

        return {
            "name": vm_name,
            "exists": True,
            "power_state": str(runtime.powerState),
            "guest_os": config.guestFullName,
            # CPU stats
            "cpu_allocated": cpu_allocated,
            "cpu_usage_mhz": cpu_usage_mhz,
            # Memory stats
            "memory_allocated_gb": round(memory_allocated_mb / 1024, 2),
            "memory_usage_gb": round(memory_usage_mb / 1024, 2),
            "memory_usage_percent": round(memory_usage_percent, 1),
            "memory_active_gb": round(memory_active_mb / 1024, 2),
            "memory_active_percent": round(memory_active_percent, 1),
            # Storage stats
            "storage_committed_gb": storage_committed_gb,
            "storage_uncommitted_gb": storage_uncommitted_gb,
            "storage_total_gb": storage_committed_gb + storage_uncommitted_gb,
            # VMware Tools
            "tools_status": str(vm.guest.toolsRunningStatus),
            "tools_version": vm.guest.toolsVersion or "Unknown",
            # Uptime
            "uptime_seconds": quick_stats.uptimeSeconds or 0,
        }

    def generate_right_sizing_recommendation(self, stats: Dict) -> Dict:
        """Generate right-sizing recommendation based on actual usage."""
        if not stats["exists"] or stats["power_state"] != "poweredOn":
            return {
                "action": "none",
                "reason": "VM not running or not found",
            }

        memory_allocated = stats["memory_allocated_gb"]
        memory_active = stats["memory_active_gb"]
        memory_usage_percent = stats["memory_usage_percent"]

        # Conservative right-sizing rules for homelab:
        # - If using < 50% of allocated memory, consider downsizing
        # - Always leave 25% headroom above peak usage
        # - Minimum 4GB for management VMs

        if memory_usage_percent < 50:
            # VM is significantly over-allocated
            recommended_gb = max(4, round(memory_active * 1.25 / 4) * 4)  # Round to nearest 4GB
            savings_gb = memory_allocated - recommended_gb

            if savings_gb >= 4:  # Only recommend if saves at least 4GB
                return {
                    "action": "downsize",
                    "current_gb": memory_allocated,
                    "recommended_gb": recommended_gb,
                    "savings_gb": savings_gb,
                    "reason": f"Using only {memory_usage_percent:.1f}% of allocated memory",
                    "confidence": "high" if memory_usage_percent < 40 else "medium",
                }

        elif memory_usage_percent > 85:
            # VM is potentially under-allocated
            recommended_gb = round(memory_allocated * 1.25 / 4) * 4  # Add 25%, round to 4GB
            increase_gb = recommended_gb - memory_allocated

            return {
                "action": "upsize",
                "current_gb": memory_allocated,
                "recommended_gb": recommended_gb,
                "increase_gb": increase_gb,
                "reason": f"Using {memory_usage_percent:.1f}% of allocated memory",
                "confidence": "medium",
            }

        return {
            "action": "keep",
            "reason": f"Current allocation ({memory_allocated}GB) is appropriate for usage ({memory_usage_percent:.1f}%)",
        }

    def _get_all_vms(self) -> List[vim.VirtualMachine]:
        """Get all VMs from vCenter inventory."""
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

        return vms

    def get_cluster_capacity_summary(self) -> Dict:
        """Get cluster-wide capacity summary including all VMs."""
        # Build set of managed VM names from tier config
        managed_vm_names = set()
        for tier in self.config["tiers"].values():
            for vm_config in tier["vms"]:
                managed_vm_names.add(vm_config["name"])

        # Get all VMs from vCenter
        all_vms = self._get_all_vms()

        # Categorize and collect stats
        managed_running = {"count": 0, "memory_gb": 0.0, "vms": []}
        other_running = {"count": 0, "memory_gb": 0.0, "vms": [], "resource_pools": {}}
        other_powered_off = {"count": 0, "memory_gb": 0.0, "vms": []}

        for vm in all_vms:
            vm_name = vm.name
            power_state = str(vm.summary.runtime.powerState)
            memory_allocated_mb = vm.summary.config.memorySizeMB
            memory_allocated_gb = round(memory_allocated_mb / 1024, 2)

            # Get resource pool name
            resource_pool_name = "Default"
            try:
                if vm.resourcePool:
                    rp_name = vm.resourcePool.name
                    # Skip generic/root pool names
                    if rp_name and rp_name not in ["Resources", "root"]:
                        resource_pool_name = rp_name
            except Exception:
                pass  # Use default if we can't get resource pool

            vm_info = {
                "name": vm_name,
                "memory_gb": memory_allocated_gb,
                "resource_pool": resource_pool_name,
            }

            if vm_name in managed_vm_names:
                if power_state == "poweredOn":
                    managed_running["count"] += 1
                    managed_running["memory_gb"] += memory_allocated_gb
                    managed_running["vms"].append(vm_info)
            else:
                if power_state == "poweredOn":
                    other_running["count"] += 1
                    other_running["memory_gb"] += memory_allocated_gb
                    other_running["vms"].append(vm_info)

                    # Track by resource pool
                    if resource_pool_name not in other_running["resource_pools"]:
                        other_running["resource_pools"][resource_pool_name] = {
                            "count": 0,
                            "memory_gb": 0.0,
                        }
                    other_running["resource_pools"][resource_pool_name]["count"] += 1
                    other_running["resource_pools"][resource_pool_name]["memory_gb"] += memory_allocated_gb
                else:
                    other_powered_off["count"] += 1
                    other_powered_off["memory_gb"] += memory_allocated_gb
                    other_powered_off["vms"].append(vm_info)

        # Calculate totals
        total_physical_ram_gb = self.config["homelab"]["total_physical_ram_gb"]
        total_running_gb = managed_running["memory_gb"] + other_running["memory_gb"]
        available_headroom_gb = total_physical_ram_gb - total_running_gb

        return {
            "total_physical_ram_gb": total_physical_ram_gb,
            "managed_running": managed_running,
            "other_running": other_running,
            "other_powered_off": other_powered_off,
            "total_running_gb": total_running_gb,
            "available_headroom_gb": available_headroom_gb,
        }

    def display_cluster_capacity_summary(self, summary: Dict) -> None:
        """Display cluster capacity summary."""
        print("\n" + "=" * 80)
        print("VCF Cluster Capacity Overview")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        total_ram = summary["total_physical_ram_gb"]
        print(f"\nPhysical Cluster Capacity: {total_ram} GB")

        print(f"\nMemory Allocation by Category:")
        print("─" * 80)

        # Management VMs (Running)
        mgmt = summary["managed_running"]
        mgmt_pct = (mgmt["memory_gb"] / total_ram * 100) if total_ram > 0 else 0
        print(f"  Management VMs (Running):      {mgmt['memory_gb']:>6.1f} GB   ({mgmt_pct:>5.1f}%)  [{mgmt['count']} VMs]")

        # Other VMs (Running)
        other_run = summary["other_running"]
        other_run_pct = (other_run["memory_gb"] / total_ram * 100) if total_ram > 0 else 0
        print(f"  Other VMs (Running):           {other_run['memory_gb']:>6.1f} GB   ({other_run_pct:>5.1f}%)  [{other_run['count']} VMs]")

        # Show resource pool breakdown for other running VMs
        if other_run["resource_pools"]:
            for pool_name in sorted(other_run["resource_pools"].keys()):
                pool_data = other_run["resource_pools"][pool_name]
                print(f"    ├─ {pool_name:<26} {pool_data['memory_gb']:>6.1f} GB              [{pool_data['count']} VMs]")

        # Other VMs (Powered Off)
        other_off = summary["other_powered_off"]
        other_off_pct = (other_off["memory_gb"] / total_ram * 100) if total_ram > 0 else 0
        print(f"  Other VMs (Powered Off):       {other_off['memory_gb']:>6.1f} GB   ({other_off_pct:>5.1f}%)  [{other_off['count']} VMs]")

        print("─" * 80)

        # Total Running and Available
        total_running = summary["total_running_gb"]
        total_running_pct = (total_running / total_ram * 100) if total_ram > 0 else 0
        total_running_count = mgmt["count"] + other_run["count"]
        print(f"  Total Allocated (Running):     {total_running:>6.1f} GB   ({total_running_pct:>5.1f}%)  [{total_running_count} VMs]")

        headroom = summary["available_headroom_gb"]
        headroom_pct = (headroom / total_ram * 100) if total_ram > 0 else 0
        print(f"  Available Headroom:            {headroom:>6.1f} GB   ({headroom_pct:>5.1f}%)")

        # Capacity Status
        print()
        if total_running_pct >= 85:
            print("Capacity Status: 🚨 CRITICAL - Low headroom available")
        elif total_running_pct >= 70:
            print("Capacity Status: ⚠ WARNING - Moderate headroom")
        else:
            print("Capacity Status: ✓ HEALTHY - Sufficient headroom available")

        # List powered-off VMs if any exist
        if other_off["count"] > 0:
            print(f"\nPowered-Off VMs You Could Start:")

            # Sort by memory (largest first)
            sorted_vms = sorted(
                other_off["vms"],
                key=lambda x: x["memory_gb"],
                reverse=True
            )

            for vm_info in sorted_vms:
                vm_memory = vm_info["memory_gb"]
                headroom_usage_pct = (vm_memory / headroom * 100) if headroom > 0 else float('inf')

                if headroom > 0 and vm_memory <= headroom:
                    print(f"  • {vm_info['name']} ({vm_memory:.1f} GB) - Would use {headroom_usage_pct:.0f}% of available headroom")
                else:
                    print(f"  • {vm_info['name']} ({vm_memory:.1f} GB) - ⚠ Exceeds available headroom")

    def audit_vm(self, vm_name: str, vm_config: Dict) -> None:
        """Audit a single VM and display detailed report."""
        print(f"\n{'=' * 80}")
        print(f"VM: {vm_config['display_name']} ({vm_name})")
        print(f"{'=' * 80}")

        stats = self.get_detailed_vm_stats(vm_name)

        if not stats["exists"]:
            if vm_config.get("optional", False):
                print("Status: NOT DEPLOYED (optional)")
            else:
                print("Status: NOT FOUND (expected to exist!)")
            return

        if stats["power_state"] != "poweredOn":
            print(f"Status: POWERED OFF")
            print("\nCannot audit resource usage - VM must be powered on")
            return

        # Display current configuration
        print(f"Hostname: {vm_config['hostname']}")
        print(f"Guest OS: {stats['guest_os']}")
        print(f"VMware Tools: {stats['tools_status']} (version {stats['tools_version']})")

        uptime_days = stats["uptime_seconds"] // 86400
        uptime_hours = (stats["uptime_seconds"] % 86400) // 3600
        print(f"Uptime: {uptime_days}d {uptime_hours}h")

        # Display resource allocation and usage
        print(f"\n{'Resource Allocation and Usage':^80}")
        print("-" * 80)

        print(f"\nCPU:")
        print(f"  Allocated vCPUs: {stats['cpu_allocated']}")
        print(f"  Current Usage: {stats['cpu_usage_mhz']} MHz")

        print(f"\nMemory:")
        print(f"  Allocated: {stats['memory_allocated_gb']:.1f} GB")
        print(f"  Guest Usage: {stats['memory_usage_gb']:.1f} GB ({stats['memory_usage_percent']:.1f}%)")
        print(f"  Active Memory: {stats['memory_active_gb']:.1f} GB ({stats['memory_active_percent']:.1f}%)")

        # Visual bar for memory usage
        bar_width = 50
        usage_bars = int(stats["memory_usage_percent"] / 100 * bar_width)
        print(f"  Usage: [{'█' * usage_bars}{'░' * (bar_width - usage_bars)}]")

        print(f"\nStorage:")
        print(f"  Committed: {stats['storage_committed_gb']:.2f} GB")
        print(f"  Uncommitted: {stats['storage_uncommitted_gb']:.2f} GB")
        print(f"  Total: {stats['storage_total_gb']:.2f} GB")

        # Generate and display recommendation
        recommendation = self.generate_right_sizing_recommendation(stats)

        print(f"\n{'Right-Sizing Recommendation':^80}")
        print("-" * 80)

        if recommendation["action"] == "downsize":
            print(f"✓ RECOMMENDATION: Downsize memory allocation")
            print(f"  Current: {recommendation['current_gb']:.0f} GB")
            print(f"  Recommended: {recommendation['recommended_gb']:.0f} GB")
            print(f"  Capacity Savings: {recommendation['savings_gb']:.0f} GB")
            print(f"  Reason: {recommendation['reason']}")
            print(f"  Confidence: {recommendation['confidence']}")

        elif recommendation["action"] == "upsize":
            print(f"⚠ RECOMMENDATION: Increase memory allocation")
            print(f"  Current: {recommendation['current_gb']:.0f} GB")
            print(f"  Recommended: {recommendation['recommended_gb']:.0f} GB")
            print(f"  Additional Required: {recommendation['increase_gb']:.0f} GB")
            print(f"  Reason: {recommendation['reason']}")

        elif recommendation["action"] == "keep":
            print(f"✓ RECOMMENDATION: Keep current allocation")
            print(f"  {recommendation['reason']}")

        # Show notes from config if available
        if "notes" in vm_config:
            print(f"\nNotes: {vm_config['notes']}")

    def audit_all_vms(self) -> List[Dict]:
        """Audit all management VMs and return summary statistics."""
        print("\n" + "=" * 80)
        print("VCF Management VM Capacity Audit Report")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        all_stats = []
        total_allocated_gb = 0
        total_usage_gb = 0
        total_potential_savings_gb = 0
        downsize_candidates = []

        for tier_name, tier_config in self.config["tiers"].items():
            print(f"\n{'─' * 80}")
            print(f"{tier_config['name']} ({tier_name.upper()})")
            print(f"{'─' * 80}")

            for vm_config in tier_config["vms"]:
                vm_name = vm_config["name"]
                stats = self.get_detailed_vm_stats(vm_name)

                if not stats["exists"] or stats["power_state"] != "poweredOn":
                    continue

                recommendation = self.generate_right_sizing_recommendation(stats)

                # Add to summary
                all_stats.append({
                    "tier": tier_name,
                    "vm_name": vm_name,
                    "display_name": vm_config["display_name"],
                    "stats": stats,
                    "recommendation": recommendation,
                })

                total_allocated_gb += stats["memory_allocated_gb"]
                total_usage_gb += stats["memory_usage_gb"]

                if recommendation["action"] == "downsize":
                    total_potential_savings_gb += recommendation["savings_gb"]
                    downsize_candidates.append({
                        "vm_name": vm_name,
                        "display_name": vm_config["display_name"],
                        "current_gb": recommendation["current_gb"],
                        "recommended_gb": recommendation["recommended_gb"],
                        "savings_gb": recommendation["savings_gb"],
                    })

                # Display one-line summary
                action_icon = {
                    "downsize": "⬇",
                    "upsize": "⬆",
                    "keep": "✓",
                    "none": "○",
                }[recommendation["action"]]

                print(
                    f"{action_icon} {vm_config['display_name']:<30} "
                    f"{stats['memory_allocated_gb']:>6.1f}GB → "
                    f"{stats['memory_usage_gb']:>6.1f}GB used "
                    f"({stats['memory_usage_percent']:>5.1f}%)"
                )

        # Print summary
        print("\n" + "=" * 80)
        print("CAPACITY AUDIT SUMMARY")
        print("=" * 80)

        homelab = self.config["homelab"]
        print(f"\nCluster Physical RAM: {homelab['total_physical_ram_gb']} GB")
        print(f"Total Allocated to Management VMs: {total_allocated_gb:.1f} GB ({total_allocated_gb / homelab['total_physical_ram_gb'] * 100:.1f}%)")
        print(f"Total Actually Used: {total_usage_gb:.1f} GB ({total_usage_gb / homelab['total_physical_ram_gb'] * 100:.1f}%)")
        print(f"Wasted Allocation: {total_allocated_gb - total_usage_gb:.1f} GB")

        if downsize_candidates:
            print(f"\n{'Right-Sizing Opportunities':^80}")
            print("-" * 80)
            print(f"\nFound {len(downsize_candidates)} VMs that can be downsized:")
            print(
                f"\n{'VM':<30} {'Current':>10} {'Recommended':>12} {'Savings':>10}"
            )
            print("-" * 80)

            for candidate in downsize_candidates:
                print(
                    f"{candidate['display_name']:<30} "
                    f"{candidate['current_gb']:>8.0f}GB "
                    f"{candidate['recommended_gb']:>10.0f}GB "
                    f"{candidate['savings_gb']:>8.0f}GB"
                )

            print("-" * 80)
            print(f"{'TOTAL POTENTIAL SAVINGS':<30} {'':<20} {total_potential_savings_gb:>8.0f}GB")
            print(
                f"\nRight-sizing would reduce management VM overhead by {total_potential_savings_gb / homelab['total_physical_ram_gb'] * 100:.1f}% of cluster capacity"
            )
        else:
            print("\n✓ No significant right-sizing opportunities found")
            print("  All management VMs are appropriately sized for their current usage")

        # Add cluster capacity summary
        cluster_summary = self.get_cluster_capacity_summary()
        self.display_cluster_capacity_summary(cluster_summary)

        return all_stats

    def export_to_csv(self, stats: List[Dict], output_path: str) -> None:
        """Export audit results to CSV file."""
        with open(output_path, "w", newline="") as csvfile:
            fieldnames = [
                "Tier",
                "VM Name",
                "Display Name",
                "Power State",
                "CPU Allocated",
                "Memory Allocated GB",
                "Memory Usage GB",
                "Memory Usage %",
                "Memory Active GB",
                "Storage Committed GB",
                "Storage Total GB",
                "Recommendation",
                "Recommended Memory GB",
                "Potential Savings GB",
            ]

            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for entry in stats:
                vm_stats = entry["stats"]
                recommendation = entry["recommendation"]

                writer.writerow({
                    "Tier": entry["tier"],
                    "VM Name": entry["vm_name"],
                    "Display Name": entry["display_name"],
                    "Power State": vm_stats["power_state"],
                    "CPU Allocated": vm_stats["cpu_allocated"],
                    "Memory Allocated GB": vm_stats["memory_allocated_gb"],
                    "Memory Usage GB": vm_stats["memory_usage_gb"],
                    "Memory Usage %": vm_stats["memory_usage_percent"],
                    "Memory Active GB": vm_stats["memory_active_gb"],
                    "Storage Committed GB": vm_stats["storage_committed_gb"],
                    "Storage Total GB": vm_stats["storage_total_gb"],
                    "Recommendation": recommendation["action"],
                    "Recommended Memory GB": recommendation.get("recommended_gb", ""),
                    "Potential Savings GB": recommendation.get("savings_gb", ""),
                })

        print(f"\n✓ Audit results exported to: {output_path}")


def main():
    """Main entry point for VCF capacity audit CLI."""
    parser = argparse.ArgumentParser(
        description="Audit VCF 9.x management VM capacity usage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--config",
        default="config/vcf-management-tiers.yaml",
        help="Path to tier configuration file",
    )

    parser.add_argument(
        "--vm-name",
        help="Audit specific VM by name (e.g., 'opsfm01')",
    )

    parser.add_argument(
        "--export-csv",
        metavar="FILE",
        help="Export audit results to CSV file",
    )

    parser.add_argument(
        "--cluster-summary-only",
        action="store_true",
        help="Show only cluster capacity summary (fast)",
    )

    args = parser.parse_args()

    # Create auditor instance
    try:
        auditor = VCFCapacityAuditor(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Execute audit
    try:
        auditor.connect_vcenter()

        if args.cluster_summary_only:
            # Quick cluster capacity summary only
            cluster_summary = auditor.get_cluster_capacity_summary()
            auditor.display_cluster_capacity_summary(cluster_summary)

        elif args.vm_name:
            # Audit specific VM
            vm_config = None
            for tier in auditor.config["tiers"].values():
                for vm in tier["vms"]:
                    if vm["name"] == args.vm_name:
                        vm_config = vm
                        break
                if vm_config:
                    break

            if not vm_config:
                print(f"Error: VM '{args.vm_name}' not found in configuration")
                sys.exit(1)

            auditor.audit_vm(args.vm_name, vm_config)

        else:
            # Audit all VMs
            stats = auditor.audit_all_vms()

            if args.export_csv:
                auditor.export_to_csv(stats, args.export_csv)

    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
    finally:
        if auditor.si:
            auditor.disconnect_vcenter()


if __name__ == "__main__":
    main()
