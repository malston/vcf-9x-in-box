#!/usr/bin/env python3
"""
ESXi USB Installer Creation Script
Purpose: Automate creation of bootable ESXi USB drives with kickstart configs
"""

import argparse
import atexit
import hashlib
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

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


# Global state for cleanup
_mounted_volume = None
_log_file = None

# Minimum USB size (8GB)
MIN_USB_SIZE = 8 * 1024 * 1024 * 1024


def cleanup():
    """Cleanup mounted volumes on exit"""
    global _mounted_volume
    if _mounted_volume:
        subprocess.run(
            ["diskutil", "unmount", _mounted_volume],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        _mounted_volume = None


def log(message: str):
    """Write message to log file if logging is enabled"""
    global _log_file
    if _log_file:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(_log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
        except (IOError, OSError):
            pass  # Silently ignore log write failures


def print_message(color: str, message: str):
    """Print colored message and log it"""
    print(f"{color}{message}{Colors.NC}")
    log(message)


def check_macos():
    """Check if running on macOS"""
    if sys.platform != "darwin":
        print(f"{Colors.RED}ERROR: This script is for macOS only{Colors.NC}")
        print(f"Current platform: {sys.platform}")
        sys.exit(1)


def validate_iso(iso_path: str) -> bool:
    """Verify file is actually an ISO"""
    if not Path(iso_path).exists():
        return False

    try:
        result = subprocess.run(
            ["file", iso_path], capture_output=True, text=True, check=True
        )
        if "ISO 9660" in result.stdout:
            print_message(Colors.GREEN, f"✓ Valid ISO file found")
            return True
        else:
            print_message(Colors.RED, "ERROR: File is not a valid ISO image")
            return False
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_message(Colors.YELLOW, "Warning: Could not verify ISO format")
        return True  # Assume valid if file command fails


def is_removable_disk(device: str) -> bool:
    """Check if disk is actually removable media"""
    try:
        output = subprocess.run(
            ["diskutil", "info", device],
            capture_output=True,
            text=True,
            check=True,
        )

        # Check for disk0 (always internal)
        if "disk0" in device:
            return False

        # Check Removable Media field
        for line in output.stdout.splitlines():
            if "Removable Media:" in line:
                if "Removable" in line:
                    return True

        # Check Protocol field - USB is typically removable
        for line in output.stdout.splitlines():
            if "Protocol:" in line:
                if "USB" in line:
                    return True

        return False

    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_disk_type(device: str) -> str:
    """Get disk type description"""
    if "disk0" in device:
        return "Internal (System)"

    try:
        output = subprocess.run(
            ["diskutil", "info", device],
            capture_output=True,
            text=True,
            check=True,
        )

        protocol = ""
        removable = ""

        for line in output.stdout.splitlines():
            if "Protocol:" in line:
                protocol = line.split(":", 1)[1].strip()
            if "Removable Media:" in line:
                removable = line.split(":", 1)[1].strip()

        if "Removable" in removable:
            return f"Removable ({protocol})"
        elif protocol == "USB":
            return "USB"
        elif protocol in ["SATA", "PCI-Express", "NVMe"]:
            return f"Internal ({protocol})"
        else:
            return protocol

    except (subprocess.CalledProcessError, FileNotFoundError):
        return "Unknown"


def list_disks():
    """List available disk devices with formatted output"""
    print()
    print_message(Colors.YELLOW, "Available disks:")
    print()

    try:
        # Get all disk devices
        result = subprocess.run(
            ["diskutil", "list"], capture_output=True, text=True, check=True
        )

        # Extract disk numbers
        disks = []
        for line in result.stdout.splitlines():
            if "/dev/disk" in line:
                disk_num = line.split("/dev/disk")[1].split()[0]
                if disk_num and disk_num[0].isdigit():
                    disks.append(disk_num.split("s")[0])  # Remove slice number

        disks = sorted(set(disks), key=lambda x: int(x))

        # Print header
        print(f"{'DISK':<8} {'NAME':<25} {'SIZE':<12} {'TYPE':<20}")
        print(f"{'----':<8} {'----':<25} {'----':<12} {'----':<20}")

        # Print disk info
        for disk_num in disks:
            device = f"/dev/disk{disk_num}"

            try:
                info = subprocess.run(
                    ["diskutil", "info", device],
                    capture_output=True,
                    text=True,
                    check=True,
                )

                disk_name = ""
                disk_size = ""

                for line in info.stdout.splitlines():
                    if "Device / Media Name:" in line or "Media Name:" in line:
                        disk_name = line.split(":", 1)[1].strip()
                    if "Disk Size:" in line:
                        parts = line.split(":", 1)[1].strip().split()
                        if len(parts) >= 2:
                            disk_size = f"{parts[0]} {parts[1]}"

                # Truncate long names
                if len(disk_name) > 25:
                    disk_name = disk_name[:22] + "..."

                disk_type = get_disk_type(device)

                # Color code based on type
                if disk_num == "0":
                    print(
                        f"{Colors.RED}disk{disk_num:<4} {disk_name:<25} {disk_size:<12} {disk_type:<20}{Colors.NC}"
                    )
                elif is_removable_disk(device):
                    print(
                        f"{Colors.GREEN}disk{disk_num:<4} {disk_name:<25} {disk_size:<12} {disk_type:<20}{Colors.NC}"
                    )
                else:
                    print(
                        f"disk{disk_num:<4} {disk_name:<25} {disk_size:<12} {disk_type:<20}"
                    )

            except subprocess.CalledProcessError:
                continue

        print()
        print(
            f"{Colors.BLUE}Legend: {Colors.RED}Internal System Disk{Colors.NC} | {Colors.GREEN}Removable/USB{Colors.NC}"
        )
        print()

    except (subprocess.CalledProcessError, FileNotFoundError):
        print_message(Colors.RED, "ERROR: Failed to list disks")
        sys.exit(1)


def get_disk_info(device: str) -> Optional[Dict[str, str]]:
    """Get detailed disk information"""
    try:
        output = subprocess.run(
            ["diskutil", "info", device],
            capture_output=True,
            text=True,
            check=True,
        )

        info = {
            "device": device,
            "name": "",
            "size": "",
            "type": "",
            "protocol": "",
            "size_bytes": 0,
        }

        for line in output.stdout.splitlines():
            if "Device / Media Name:" in line or "Media Name:" in line:
                info["name"] = line.split(":", 1)[1].strip()
            if "Disk Size:" in line:
                parts = line.split(":", 1)[1].strip().split()
                info["size"] = f"{parts[0]} {parts[1]}"
                # Extract bytes value (in parentheses)
                for part in parts:
                    if part.startswith("(") and part.endswith(")"):
                        try:
                            info["size_bytes"] = int(part.strip("()"))
                        except ValueError:
                            pass
            if "Protocol:" in line:
                info["protocol"] = line.split(":", 1)[1].strip()

        info["type"] = get_disk_type(device)
        return info

    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def show_disk_info(device: str):
    """Display detailed disk information"""
    info = get_disk_info(device)
    if not info:
        print_message(Colors.RED, f"ERROR: Could not get info for {device}")
        return

    print(f"{Colors.BLUE}Device Information:{Colors.NC}")
    print(f"  Device:   {info['device']}")
    print(f"  Name:     {info['name']}")
    print(f"  Size:     {info['size']}")
    print(f"  Type:     {info['type']}")
    print(f"  Protocol: {info['protocol']}")

    # Show partitions
    try:
        result = subprocess.run(
            ["diskutil", "list", device],
            capture_output=True,
            text=True,
            check=True,
        )
        partitions = [
            line for line in result.stdout.splitlines() if line.strip().startswith("0:")
        ]
        if partitions:
            print(f"\n  Partitions:")
            for part in partitions:
                print(f"    {part}")
    except subprocess.CalledProcessError:
        pass

    print()


def calculate_sha256(file_path: str, max_bytes: Optional[int] = None) -> str:
    """Calculate SHA256 hash of a file"""
    sha256 = hashlib.sha256()
    bytes_read = 0

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            if max_bytes and bytes_read + len(chunk) > max_bytes:
                chunk = chunk[: max_bytes - bytes_read]
                sha256.update(chunk)
                break
            sha256.update(chunk)
            bytes_read += len(chunk)

    return sha256.hexdigest()


def verify_checksum(iso_path: str, device: str, iso_size: int, skip_confirm: bool = False) -> bool:
    """Verify written data matches ISO"""
    print_message(
        Colors.YELLOW, "Verifying write integrity (this may take a few minutes)..."
    )

    # Unmount any auto-mounted volumes
    disk_num = device.split("disk")[1].split("s")[0] if "disk" in device else None
    if disk_num:
        base_disk = f"/dev/disk{disk_num}"
        subprocess.run(
            ["diskutil", "unmountDisk", base_disk],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    try:
        # Calculate ISO checksum
        print_message(Colors.BLUE, "Computing ISO checksum...")
        iso_checksum = calculate_sha256(iso_path)
        log(f"ISO SHA256: {iso_checksum}")

        # Calculate disk checksum (read back the same number of bytes)
        print_message(Colors.BLUE, "Computing disk checksum...")
        disk_checksum = calculate_sha256(device, iso_size)
        log(f"Disk SHA256: {disk_checksum}")

        if iso_checksum == disk_checksum:
            print_message(Colors.GREEN, "✓ Checksum verification passed")
            return True
        else:
            print_message(Colors.RED, "✗ Checksum verification failed!")
            print_message(Colors.YELLOW, f"ISO:  {iso_checksum}")
            print_message(Colors.YELLOW, f"Disk: {disk_checksum}")
            print_message(
                Colors.YELLOW,
                "This often happens on macOS when the system auto-mounts the USB",
            )
            print_message(
                Colors.YELLOW,
                "and adds hidden files (.Spotlight-V100, .fseventsd, etc.)",
            )
            print_message(
                Colors.BLUE, "If the USB boots ESXi correctly, it's likely fine"
            )

            if skip_confirm:
                print_message(Colors.YELLOW, "Continuing anyway (--yes flag enabled)")
                return True
            else:
                print()
                response = input("Continue anyway? (yes/no): ")
                return response.lower() == "yes"

    except Exception as e:
        print_message(Colors.RED, f"ERROR: Checksum verification failed: {e}")
        return False


def load_config(config_file: Path) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    if not config_file.exists():
        print(f"{Colors.RED}ERROR: Config file not found: {config_file}{Colors.NC}")
        sys.exit(1)

    try:
        with open(config_file, "r", encoding="utf-8") as f:
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
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"{Colors.RED}ERROR: Failed to load config: {e}{Colors.NC}")
        sys.exit(1)


def run_command(cmd: list, capture_output: bool = False) -> Optional[str]:
    """Run a shell command and handle errors"""
    try:
        if capture_output:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout
        else:
            subprocess.run(cmd, check=True)
            return None
    except subprocess.CalledProcessError as e:
        print_message(Colors.RED, f"ERROR: Command failed: {' '.join(cmd)}")
        if capture_output and e.stderr:
            print_message(Colors.RED, e.stderr)
        sys.exit(1)


def check_root(dry_run: bool = False):
    """Check if script is running with sudo/root privileges"""
    if dry_run:
        return  # Skip root check in dry-run mode

    if os.geteuid() != 0:
        print_message(Colors.RED, "ERROR: This script must be run with sudo")
        print("Example: sudo python3 scripts/create_esxi_usb.py /dev/disk2 1")
        sys.exit(1)


def confirm_action(message: str, skip_confirm: bool = False) -> bool:
    """Ask user for confirmation"""
    if skip_confirm:
        return True

    print_message(Colors.YELLOW, message)
    response = input("Continue? (yes/no): ")
    if response.lower() != "yes":
        print_message(Colors.RED, "Operation cancelled by user")
        sys.exit(1)
    return True


def validate_disk_selection(device: str, skip_confirm: bool = False) -> bool:
    """Validate disk selection with enhanced safety checks"""
    # Prevent selecting disk0
    if "disk0" in device:
        print_message(Colors.RED, "FATAL ERROR: Cannot select disk0 (internal system disk)!")
        print_message(Colors.YELLOW, "Selecting disk0 would erase your macOS installation!")
        return False

    # Check if disk exists
    if not Path(device).exists():
        print_message(Colors.RED, f"ERROR: Device {device} does not exist")
        print("Run 'diskutil list' or use --list to see available devices")
        return False

    # Get disk info
    info = get_disk_info(device)
    if not info:
        print_message(Colors.RED, f"ERROR: Could not get info for {device}")
        return False

    # Check disk size
    if info["size_bytes"] > 0 and info["size_bytes"] < MIN_USB_SIZE:
        size_gb = info["size_bytes"] / (1024 * 1024 * 1024)
        print_message(
            Colors.YELLOW,
            f"Warning: Disk size ({size_gb:.1f}GB) is less than recommended 8GB for ESXi",
        )
        print_message(Colors.YELLOW, "Installation may fail or have limited functionality")

    # Warn if not removable
    if not is_removable_disk(device):
        print_message(
            Colors.YELLOW,
            f"WARNING: {device} does not appear to be a removable USB drive",
        )
        print_message(
            Colors.YELLOW,
            "This may be an internal disk or connected via another protocol",
        )
        print()

        if skip_confirm:
            print_message(
                Colors.RED,
                "ERROR: Cannot use --yes with non-removable disks (safety feature)",
            )
            return False

        response = input("Are you absolutely sure you want to use this disk? (type 'I AM SURE'): ")
        if response != "I AM SURE":
            print_message(Colors.YELLOW, "Operation cancelled")
            return False

    return True


def verify_usb_device(device: str, skip_confirm: bool = False, dry_run: bool = False):
    """Verify USB device exists and is valid"""
    # Enhanced validation
    if not dry_run:
        if not validate_disk_selection(device, skip_confirm):
            sys.exit(1)

    # Check if device exists
    if not Path(device).exists():
        if dry_run:
            print_message(
                Colors.YELLOW, f"⚠ Device {device} does not exist (would fail in real run)"
            )
            return
        else:
            print_message(Colors.RED, f"ERROR: Device {device} does not exist")
            print("Run 'diskutil list' to see available devices")
            sys.exit(1)

    # Show device info
    show_disk_info(device)


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
            print_message(Colors.YELLOW, "========================================")
            print_message(Colors.YELLOW, "DRY RUN MODE - No changes will be made")
            print_message(Colors.YELLOW, "========================================\n")

        # Validate host number
        if host_num not in self.config["hosts_dict"]:
            print_message(
                Colors.RED, f"ERROR: Host {host_num} not found in config file"
            )
            print(f"Available hosts: {sorted(self.config['hosts_dict'].keys())}")
            sys.exit(1)

        host_config = self.config["hosts_dict"][host_num]

        # Verify ESXi ISO exists
        if not Path(iso_path).exists():
            if dry_run:
                print_message(
                    Colors.YELLOW, f"⚠ ESXi ISO not found (would fail): {iso_path}"
                )
            else:
                print_message(
                    Colors.RED, f"ERROR: ESXi ISO not found at: {iso_path}"
                )
                print("Use -i flag to specify the correct path")
                sys.exit(1)
        else:
            print_message(Colors.GREEN, f"✓ Found ESXi ISO: {iso_path}")

        # Verify kickstart config exists
        kickstart_file = self.config_dir / f"ks-esx0{host_num}.cfg"
        if not kickstart_file.exists():
            if dry_run:
                print_message(
                    Colors.YELLOW, f"⚠ Kickstart config not found (would fail): {kickstart_file}"
                )
            else:
                print_message(
                    Colors.RED, f"ERROR: Kickstart config not found: {kickstart_file}"
                )
                print("Run 'make generate' first to generate kickstart configs")
                sys.exit(1)
        else:
            print_message(
                Colors.GREEN, f"✓ Found kickstart config: {kickstart_file}"
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
                check=False,
            )

        # Write ISO to USB
        raw_device = usb_device.replace("disk", "rdisk")
        iso_size_bytes = Path(iso_path).stat().st_size
        iso_size_mb = iso_size_bytes / (1024 * 1024)

        if dry_run:
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would write ESXi ISO to {raw_device}"
            )
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Command: dd if={iso_path} of={raw_device} bs=1m"
            )
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} ISO size: {iso_size_mb:.1f} MB"
            )
        else:
            print_message(
                Colors.YELLOW,
                f"Writing ESXi ISO to USB device ({iso_size_mb:.1f}MB)...",
            )
            print_message(
                Colors.YELLOW, "This may take 10-20 minutes depending on USB speed..."
            )
            print()

            # Track timing
            start_time = time.time()

            # Use dd with status=progress
            try:
                subprocess.run(
                    ["dd", f"if={iso_path}", f"of={raw_device}", "bs=1m", "status=progress"],
                    check=True,
                )
            except subprocess.CalledProcessError:
                print_message(Colors.RED, "ERROR: Failed to write ISO to USB drive")
                print_message(
                    Colors.YELLOW,
                    "Suggestion: Check if the disk is write-protected or try a different USB drive",
                )
                sys.exit(1)

            # Ensure all data is flushed to disk
            print_message(Colors.YELLOW, "Syncing data to disk...")
            subprocess.run(["sync"], check=False)

            end_time = time.time()
            duration = int(end_time - start_time)
            speed_mbps = iso_size_mb / duration if duration > 0 else 0

            print_message(
                Colors.GREEN, f"✓ ISO written to USB device (took {duration}s, {speed_mbps:.1f} MB/s)"
            )

        # Verify checksum
        if not dry_run:
            if not verify_checksum(iso_path, raw_device, iso_size_bytes, skip_confirm):
                print_message(Colors.RED, "Checksum verification failed")
                sys.exit(1)
        else:
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would verify checksum of written data"
            )

        # Wait for system to recognize filesystem
        if dry_run:
            print(
                f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would wait 3 seconds for filesystem recognition"
            )
        else:
            print_message(
                Colors.YELLOW, "Waiting for filesystem to be recognized..."
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
                if output is None:
                    print(
                        f"{Colors.RED}ERROR: Could not get device info for {usb_partition}{Colors.NC}"
                    )
                    sys.exit(1)

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
                subprocess.run(["sync"], check=False)
                subprocess.run(
                    ["diskutil", "unmount", mount_point],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                subprocess.run(["diskutil", "eject", usb_device], check=False)
                print_message(Colors.GREEN, "✓ USB device ejected")

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
            print_message(Colors.YELLOW, "DRY RUN Complete - No changes made")
        else:
            print_message(Colors.GREEN, "USB Creation Complete!")
        print(f"{Colors.GREEN}========================================{Colors.NC}\n")

        print(f"USB Device:    {usb_device}")
        print(f"ESXi Host:     {host_config['hostname']}")
        print(f"Host IP:       {host_config['ip']}")
        print(f"Kickstart:     KS.CFG (from ks-esx0{host_num}.cfg)")
        log(f"Created USB for {host_config['hostname']} on {usb_device}")
        print()
        print_message(Colors.YELLOW, "Next Steps:")
        print("1. Remove USB drive from computer")
        print(f"2. Insert USB into MS-A2 host #{host_num} ({host_config['hostname']})")
        print("3. Power on the MS-A2")
        print("4. Press F11 (or appropriate boot menu key) to select USB boot")
        print("5. Installation will proceed automatically")
        print("6. Host will reboot twice during installation")
        print("7. After final reboot, host will be accessible at:")
        print(f"   https://{host_config['ip']} or https://{host_config['hostname']}")
        print()
        print_message(Colors.GREEN, "Login Credentials:")
        print("  Username: root")
        print(f"  Password: {self.config['common']['root_password']}")
        print()


def main():
    global _log_file

    parser = argparse.ArgumentParser(
        description="Create bootable ESXi USB drives with kickstart configs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --interactive                  # Interactive mode with disk selection
  %(prog)s --dry-run /dev/disk2 1         # Dry run (no root required)
  sudo %(prog)s /dev/disk2 1              # Create USB for ESX01
  sudo %(prog)s /dev/disk3 2              # Create USB for ESX02
  sudo %(prog)s /dev/disk2 3 -y           # Create USB for ESX03, skip confirmation
  %(prog)s --list                         # List available USB devices
  sudo %(prog)s /dev/disk2 1 --log usb.log  # With logging

Interactive mode:
  %(prog)s --interactive                  # Guided USB creation

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

    parser.add_argument(
        "--interactive", action="store_true", help="Interactive mode with disk selection"
    )

    parser.add_argument(
        "--log", type=str, help="Write detailed log to file"
    )

    args = parser.parse_args()

    # Setup logging
    if args.log:
        _log_file = args.log
        try:
            with open(_log_file, "w", encoding="utf-8") as f:
                f.write(f"ESXi USB Creator Log - {datetime.now()}\n")
            log("Log started")
        except (IOError, OSError) as e:
            print(f"{Colors.YELLOW}Warning: Could not create log file: {e}{Colors.NC}")
            _log_file = None

    # Setup signal handlers and cleanup
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda _s, _f: (cleanup(), sys.exit(1)))

    # Check macOS
    check_macos()

    # Handle --list option
    if args.list:
        print_message(Colors.GREEN, "Available Disk Devices:")
        list_disks()
        sys.exit(0)

    # Interactive mode or validate required arguments
    if args.interactive or (not args.usb_device or args.host_number is None):
        # Determine script and config directories first
        script_dir = Path(__file__).resolve().parent
        project_dir = script_dir.parent
        config_dir = project_dir / "config"
        config_file = args.config if args.config else config_dir / "vcf-config.yaml"

        # Load configuration to show available hosts
        config = load_config(config_file)

        # Print header
        print(f"{Colors.GREEN}========================================{Colors.NC}")
        print(f"{Colors.GREEN}ESXi USB Installer Creation Script{Colors.NC}")
        print(f"{Colors.GREEN}Interactive Mode{Colors.NC}")
        print(f"{Colors.GREEN}========================================{Colors.NC}\n")

        # Show available disks
        list_disks()

        # Get disk selection
        while True:
            disk_input = input("Enter disk number (e.g., 2 for /dev/disk2): ").strip()
            if disk_input.isdigit():
                args.usb_device = f"/dev/disk{disk_input}"
                if Path(args.usb_device).exists():
                    break
                else:
                    print_message(Colors.RED, f"ERROR: {args.usb_device} not found")
            else:
                print_message(Colors.RED, "ERROR: Invalid disk number")

        # Show available hosts
        print()
        print_message(Colors.YELLOW, "Available ESXi hosts:")
        for host_num in sorted(config["hosts_dict"].keys()):
            host = config["hosts_dict"][host_num]
            print(f"  {host_num}: {host['hostname']} ({host['ip']})")
        print()

        # Get host selection
        while True:
            host_input = input("Enter host number: ").strip()
            if host_input.isdigit() and int(host_input) in config["hosts_dict"]:
                args.host_number = int(host_input)
                break
            else:
                print_message(Colors.RED, "ERROR: Invalid host number")
        print()

    else:
        # Non-interactive: validate required arguments
        if not args.usb_device or args.host_number is None:
            print_message(Colors.RED, "ERROR: Missing required arguments")
            print("Use --interactive for guided mode, or provide device and host number")
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

    # Load configuration (may have been loaded already in interactive mode)
    config = load_config(config_file)

    # Get ESXi ISO path from config or command line
    if args.iso:
        iso_path = str(args.iso)
    elif "esxi_iso_path" in config.get("common", {}):
        iso_path = config["common"]["esxi_iso_path"]
    else:
        # Default path
        print_message(Colors.RED, "ERROR: ESXi ISO path not specified")
        print("Please specify the ESXi ISO path using one of these methods:")
        print("1. Use the -i/--iso command line option:")
        print(
            "   Example: sudo uv run scripts/create_esxi_usb.py /dev/disk2 1 -i /path/to/esxi.iso"
        )
        print("2. Add 'esxi_iso_path' to the 'common' section in your config file")
        sys.exit(1)

    # Validate ISO
    print(f"ISO: {Path(iso_path).name}")
    if not validate_iso(iso_path):
        sys.exit(1)

    # Print header (if not already in interactive mode)
    if not args.interactive:
        print(f"\n{Colors.GREEN}========================================{Colors.NC}")
        print(f"{Colors.GREEN}ESXi USB Installer Creation Script{Colors.NC}")
        print(f"{Colors.GREEN}========================================{Colors.NC}\n")

    # Create USB
    creator = USBCreator(config, config_dir)
    try:
        creator.create_usb(
            args.usb_device, args.host_number, iso_path, args.yes, args.dry_run
        )
        if _log_file:
            print_message(Colors.BLUE, f"Log saved to: {_log_file}")
    except KeyboardInterrupt:
        print()
        print_message(Colors.YELLOW, "Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_message(Colors.RED, f"ERROR: {e}")
        if _log_file:
            print_message(Colors.BLUE, f"Check log for details: {_log_file}")
        sys.exit(1)


if __name__ == "__main__":
    main()
