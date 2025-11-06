#!/usr/bin/env python3
"""
ESXi USB Installer Creation Script
Purpose: Automate creation of bootable ESXi USB drives with kickstart configs
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml module not found. Install with: pip install pyyaml")
    sys.exit(1)


# Color output
class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color


def load_config(config_file: Path) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    if not config_file.exists():
        print(f"{Colors.RED}ERROR: Config file not found: {config_file}{Colors.NC}")
        sys.exit(1)

    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)

        # Validate required sections
        required_sections = ["network", "common", "hosts"]
        for section in required_sections:
            if section not in config:
                print(
                    f"{Colors.RED}ERROR: Missing '{section}' section in config file{Colors.NC}"
                )
                sys.exit(1)

        # Convert hosts list to dict for easier access
        hosts_dict = {}
        for host in config["hosts"]:
            hosts_dict[host["number"]] = host

        config["hosts_dict"] = hosts_dict
        return config

    except yaml.YAMLError as e:
        print(f"{Colors.RED}ERROR: Failed to parse YAML config: {e}{Colors.NC}")
        sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}ERROR: Failed to load config: {e}{Colors.NC}")
        sys.exit(1)


def run_command(
    cmd: list, description: str = "", capture_output: bool = False
) -> Optional[str]:
    """Run a shell command and handle errors"""
    try:
        if capture_output:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout
        else:
            subprocess.run(cmd, check=True)
            return None
    except subprocess.CalledProcessError as e:
        print(f"{Colors.RED}ERROR: Command failed: {' '.join(cmd)}{Colors.NC}")
        if capture_output and e.stderr:
            print(f"{Colors.RED}{e.stderr}{Colors.NC}")
        sys.exit(1)


def check_root(dry_run: bool = False):
    """Check if script is running with sudo/root privileges"""
    if dry_run:
        return  # Skip root check in dry-run mode

    if os.geteuid() != 0:
        print(f"{Colors.RED}ERROR: This script must be run with sudo{Colors.NC}")
        print("Example: sudo python3 scripts/create_esxi_usb.py /dev/disk2 1")
        sys.exit(1)


def confirm_action(message: str, skip_confirm: bool = False) -> bool:
    """Ask user for confirmation"""
    if skip_confirm:
        return True

    print(f"{Colors.YELLOW}{message}{Colors.NC}")
    response = input("Continue? (yes/no): ")
    if response.lower() != "yes":
        print(f"{Colors.RED}Operation cancelled by user{Colors.NC}")
        sys.exit(1)
    return True


def verify_usb_device(device: str, skip_confirm: bool = False, dry_run: bool = False):
    """Verify USB device exists and is valid"""
    # Check if device exists
    if not Path(device).exists():
        if dry_run:
            print(
                f"{Colors.YELLOW}⚠{Colors.NC} Device {device} does not exist (would fail in real run)"
            )
            return
        else:
            print(f"{Colors.RED}ERROR: Device {device} does not exist{Colors.NC}")
            print("Run 'diskutil list' to see available devices")
            sys.exit(1)

    # Get device info
    try:
        output = run_command(["diskutil", "info", device], capture_output=True)

        # Extract relevant info
        device_name = ""
        total_size = ""
        protocol = ""

        for line in output.splitlines():
            if "Device / Media Name:" in line:
                device_name = line.split(":", 1)[1].strip()
            elif "Total Size:" in line:
                total_size = line.split(":", 1)[1].strip()
            elif "Protocol:" in line:
                protocol = line.split(":", 1)[1].strip()

        print(f"{Colors.BLUE}Device Information:{Colors.NC}")
        if device_name:
            print(f"  Name: {device_name}")
        if total_size:
            print(f"  Size: {total_size}")
        print()

        # Safety check - ensure it's removable media
        if protocol != "USB" and not skip_confirm and not dry_run:
            print(
                f"{Colors.YELLOW}WARNING: Device does not appear to be USB (Protocol: {protocol}){Colors.NC}"
            )
            confirm_action("Are you sure you want to continue?")
        elif protocol != "USB" and dry_run:
            print(
                f"{Colors.YELLOW}WARNING: Device does not appear to be USB (Protocol: {protocol}){Colors.NC}"
            )

    except Exception as e:
        print(f"{Colors.RED}ERROR: Unable to get info for device {device}{Colors.NC}")
        sys.exit(1)


class USBCreator:
    """Create bootable ESXi USB drives with kickstart configs"""

    def __init__(self, config: Dict[str, Any], config_dir: Path):
        self.config = config
        self.config_dir = config_dir

    def create_usb(
        self,
        usb_device: str,
        host_num: int,
        iso_path: str,
        skip_confirm: bool = False,
        dry_run: bool = False,
    ):
        """Create bootable ESXi USB for specific host"""

        if dry_run:
            print(f"{Colors.YELLOW}========================================{Colors.NC}")
            print(f"{Colors.YELLOW}DRY RUN MODE - No changes will be made{Colors.NC}")
            print(
                f"{Colors.YELLOW}========================================{Colors.NC}\n"
            )

        # Validate host number
        if host_num not in self.config["hosts_dict"]:
            print(
                f"{Colors.RED}ERROR: Host {host_num} not found in config file{Colors.NC}"
            )
            print(f"Available hosts: {sorted(self.config['hosts_dict'].keys())}")
            sys.exit(1)

        host_config = self.config["hosts_dict"][host_num]

        # Verify ESXi ISO exists
        if not Path(iso_path).exists():
            if dry_run:
                print(
                    f"{Colors.YELLOW}⚠{Colors.NC} ESXi ISO not found (would fail): {iso_path}"
                )
            else:
                print(
                    f"{Colors.RED}ERROR: ESXi ISO not found at: {iso_path}{Colors.NC}"
                )
                print("Use -i flag to specify the correct path")
                sys.exit(1)
        else:
            print(f"{Colors.GREEN}✓{Colors.NC} Found ESXi ISO: {iso_path}")

        # Verify kickstart config exists
        kickstart_file = self.config_dir / f"ks-esx0{host_num}.cfg"
        if not kickstart_file.exists():
            if dry_run:
                print(
                    f"{Colors.YELLOW}⚠{Colors.NC} Kickstart config not found (would fail): {kickstart_file}"
                )
            else:
                print(
                    f"{Colors.RED}ERROR: Kickstart config not found: {kickstart_file}{Colors.NC}"
                )
                print("Run 'make generate' first to generate kickstart configs")
                sys.exit(1)
        else:
            print(
                f"{Colors.GREEN}✓{Colors.NC} Found kickstart config: {kickstart_file}"
            )

        # Verify USB device
        verify_usb_device(usb_device, skip_confirm, dry_run)

        # Final confirmation
        if not skip_confirm and not dry_run:
            print(f"{Colors.RED}========================================{Colors.NC}")
            print(
                f"{Colors.RED}WARNING: ALL DATA ON {usb_device} WILL BE ERASED!{Colors.NC}"
            )
            print(f"{Colors.RED}========================================{Colors.NC}")
            print()
            print("Configuration:")
            print(f"  USB Device:     {usb_device}")
            print(f"  ESXi Host:      {host_config['hostname']}")
            print(f"  Host IP:        {host_config['ip']}")
            print(f"  Kickstart:      {kickstart_file.name}")
            print(f"  ESXi ISO:       {iso_path}")
            print()
            confirm_action(f"This will ERASE ALL DATA on {usb_device}!")

        # Display operation plan
        print()
        print(f"{Colors.BLUE}Operation Plan:{Colors.NC}")
        print(f"  USB Device:     {usb_device}")
        print(f"  ESXi Host:      {host_config['hostname']}")
        print(f"  Host IP:        {host_config['ip']}")
        print(f"  Kickstart:      {kickstart_file.name}")
        print(f"  ESXi ISO:       {Path(iso_path).name}")
        print()

        # Unmount the USB device
        if dry_run:
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would unmount USB device: {usb_device}"
            )
        else:
            print(f"{Colors.YELLOW}Unmounting USB device...{Colors.NC}")
            subprocess.run(
                ["diskutil", "unmountDisk", usb_device],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # Write ISO to USB
        raw_device = usb_device.replace("disk", "rdisk")
        if dry_run:
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would write ESXi ISO to {raw_device}"
            )
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Command: dd if={iso_path} of={raw_device} bs=1m"
            )
        else:
            print(
                f"{Colors.YELLOW}Writing ESXi ISO to USB device (this will take several minutes)...{Colors.NC}"
            )
            print(f"{Colors.BLUE}Progress: Writing ISO to {usb_device}...{Colors.NC}")
            run_command(["dd", f"if={iso_path}", f"of={raw_device}", "bs=1m"])
            print(f"{Colors.GREEN}✓{Colors.NC} ISO written to USB device")

        # Wait for system to recognize filesystem
        if dry_run:
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would wait 3 seconds for filesystem recognition"
            )
        else:
            print(
                f"{Colors.YELLOW}Waiting for filesystem to be recognized...{Colors.NC}"
            )
            time.sleep(3)

        # Mount the USB device
        if dry_run:
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would mount USB partition: {usb_device}s1"
            )
        else:
            print(f"{Colors.YELLOW}Mounting USB device...{Colors.NC}")

        usb_partition = f"{usb_device}s1"
        mount_point = "/Volumes/ESXi"  # Typical mount point for ESXi USB

        if dry_run:
            # Copy kickstart file
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would copy kickstart to USB: {kickstart_file.name} -> {mount_point}/KS.CFG"
            )

            # Modify BOOT.CFG
            boot_cfg_path = Path(mount_point) / "EFI" / "BOOT" / "BOOT.CFG"
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would modify BOOT.CFG at: {boot_cfg_path}"
            )
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would change: kernelopt=... -> kernelopt=ks=usb:/KS.CFG"
            )
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would backup BOOT.CFG to: {boot_cfg_path}.backup"
            )

            # Unmount and eject USB
            print(f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would sync filesystem")
            print(f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would unmount: {mount_point}")
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would eject USB device: {usb_device}"
            )
        else:
            try:
                # Try to mount the partition
                run_command(["diskutil", "mount", usb_partition])

                # Get the mount point
                output = run_command(
                    ["diskutil", "info", usb_partition], capture_output=True
                )
                for line in output.splitlines():
                    if "Mount Point:" in line:
                        mount_point = line.split(":", 1)[1].strip()
                        break

                if not mount_point:
                    print(
                        f"{Colors.RED}ERROR: Could not determine mount point{Colors.NC}"
                    )
                    sys.exit(1)

                print(f"{Colors.GREEN}✓{Colors.NC} USB mounted at: {mount_point}")

                # Copy kickstart file
                print(f"{Colors.YELLOW}Copying kickstart config to USB...{Colors.NC}")
                ks_dest = Path(mount_point) / "KS.CFG"
                run_command(["cp", str(kickstart_file), str(ks_dest)])
                print(f"{Colors.GREEN}✓{Colors.NC} Copied kickstart config as KS.CFG")

                # Modify BOOT.CFG
                boot_cfg_path = Path(mount_point) / "EFI" / "BOOT" / "BOOT.CFG"
                if not boot_cfg_path.exists():
                    print(
                        f"{Colors.RED}ERROR: BOOT.CFG not found at: {boot_cfg_path}{Colors.NC}"
                    )
                    sys.exit(1)

                print(
                    f"{Colors.YELLOW}Modifying BOOT.CFG for kickstart installation...{Colors.NC}"
                )

                # Backup original BOOT.CFG
                run_command(["cp", str(boot_cfg_path), f"{boot_cfg_path}.backup"])

                # Read and modify BOOT.CFG
                boot_cfg_content = boot_cfg_path.read_text()

                # Update kernelopt line
                new_content = []
                for line in boot_cfg_content.splitlines():
                    if line.startswith("kernelopt="):
                        new_content.append("kernelopt=ks=usb:/KS.CFG")
                    else:
                        new_content.append(line)

                boot_cfg_path.write_text("\n".join(new_content) + "\n")

                print(f"{Colors.GREEN}✓{Colors.NC} Modified BOOT.CFG for kickstart")

                # Verify the change
                if "kernelopt=ks=usb:/KS.CFG" in boot_cfg_path.read_text():
                    print(f"{Colors.GREEN}✓{Colors.NC} Verified BOOT.CFG modification")
                else:
                    print(f"{Colors.RED}ERROR: BOOT.CFG modification failed{Colors.NC}")
                    sys.exit(1)

            finally:
                # Unmount and eject USB
                print(f"{Colors.YELLOW}Ejecting USB device...{Colors.NC}")
                subprocess.run(["sync"])
                subprocess.run(
                    ["diskutil", "unmount", mount_point],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                subprocess.run(["diskutil", "eject", usb_device])
                print(f"{Colors.GREEN}✓{Colors.NC} USB device ejected")

        # Summary
        self._print_summary(usb_device, host_num, host_config, dry_run)

    def _print_summary(
        self,
        usb_device: str,
        host_num: int,
        host_config: Dict[str, Any],
        dry_run: bool = False,
    ):
        """Print completion summary with next steps"""
        print(f"\n{Colors.GREEN}========================================{Colors.NC}")
        if dry_run:
            print(f"{Colors.YELLOW}DRY RUN Complete - No changes made{Colors.NC}")
        else:
            print(f"{Colors.GREEN}USB Creation Complete!{Colors.NC}")
        print(f"{Colors.GREEN}========================================{Colors.NC}\n")

        print(f"USB Device:    {usb_device}")
        print(f"ESXi Host:     {host_config['hostname']}")
        print(f"Host IP:       {host_config['ip']}")
        print(f"Kickstart:     KS.CFG (from ks-esx0{host_num}.cfg)")
        print()
        print(f"{Colors.YELLOW}Next Steps:{Colors.NC}")
        print("1. Remove USB drive from computer")
        print(f"2. Insert USB into MS-A2 host #{host_num} ({host_config['hostname']})")
        print("3. Power on the MS-A2")
        print("4. Press F11 (or appropriate boot menu key) to select USB boot")
        print("5. Installation will proceed automatically")
        print("6. Host will reboot twice during installation")
        print("7. After final reboot, host will be accessible at:")
        print(f"   https://{host_config['ip']} or https://{host_config['hostname']}")
        print()
        print(f"{Colors.GREEN}Login Credentials:{Colors.NC}")
        print("  Username: root")
        print(f"  Password: {self.config['common']['root_password']}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Create bootable ESXi USB drives with kickstart configs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run /dev/disk2 1         # Dry run (no root required)
  sudo %(prog)s /dev/disk2 1              # Create USB for ESX01
  sudo %(prog)s /dev/disk3 2              # Create USB for ESX02
  sudo %(prog)s /dev/disk2 3 -y           # Create USB for ESX03, skip confirmation
  %(prog)s --list                         # List available USB devices

To find your USB device:
  diskutil list
        """,
    )

    parser.add_argument(
        "usb_device", nargs="?", help="USB device path (e.g., /dev/disk2)"
    )

    parser.add_argument(
        "host_number", nargs="?", type=int, help="ESXi host number (1, 2, 3, etc.)"
    )

    parser.add_argument("-i", "--iso", type=Path, help="Path to ESXi ISO file")

    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="Path to YAML config file (default: config/vcf-config.yaml)",
    )

    parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompts"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making any changes",
    )

    parser.add_argument(
        "--list", action="store_true", help="List available disk devices"
    )

    args = parser.parse_args()

    # Handle --list option
    if args.list:
        print(f"{Colors.GREEN}Available Disk Devices:{Colors.NC}\n")
        subprocess.run(["diskutil", "list"])
        sys.exit(0)

    # Validate required arguments
    if not args.usb_device or args.host_number is None:
        print(f"{Colors.RED}ERROR: Missing required arguments{Colors.NC}")
        parser.print_help()
        sys.exit(1)

    # Check if running as root (skip in dry-run mode)
    check_root(args.dry_run)

    # Determine script and config directories
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent
    config_dir = project_dir / "config"

    # Determine config file
    config_file = args.config if args.config else config_dir / "vcf-config.yaml"

    # Load configuration
    config = load_config(config_file)

    # Get ESXi ISO path from config or command line
    if args.iso:
        iso_path = str(args.iso)
    elif "esxi_iso_path" in config.get("common", {}):
        iso_path = config["common"]["esxi_iso_path"]
    else:
        # Default path
        iso_path = "/Volumes/vcf-content/Software/depot/VCF9/PROD/COMP/ESX_HOST/VMware-VMvisor-Installer-9.0.0.0.24755229.x86_64.iso"

    # Print header
    print(f"{Colors.GREEN}========================================{Colors.NC}")
    print(f"{Colors.GREEN}ESXi USB Installer Creation Script{Colors.NC}")
    print(f"{Colors.GREEN}========================================{Colors.NC}\n")

    # Create USB
    creator = USBCreator(config, config_dir)
    creator.create_usb(
        args.usb_device, args.host_number, iso_path, args.yes, args.dry_run
    )


if __name__ == "__main__":
    main()
