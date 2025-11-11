#!/usr/bin/env python3
"""
rEFInd USB Boot Menu Creator for ESXi 9
Purpose: Create a single USB with custom UEFI boot menu for multiple ESXi hosts
Based on: https://williamlam.com/2025/07/custom-uefi-boot-menu-for-esxi-9-0-using-refind.html
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

import yaml


# Color output
# pylint: disable=too-few-public-methods
class Colors:
    """ANSI color codes for terminal output"""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color


def print_message(color: str, message: str):
    """Print colored message"""
    print(f"{color}{message}{Colors.NC}")


def check_macos():
    """Check if running on macOS"""
    if sys.platform != "darwin":
        print_message(Colors.RED, "ERROR: This script is for macOS only")
        print(f"Current platform: {sys.platform}")
        sys.exit(1)


def check_root(dry_run: bool = False):
    """Check if script is running with sudo/root privileges"""
    if dry_run:
        return  # Skip root check in dry-run mode

    if os.geteuid() != 0:
        print_message(Colors.RED, "ERROR: This script must be run with sudo")
        print("Example: sudo python3 scripts/create_refind_usb.py /dev/disk4")
        sys.exit(1)


def load_config(config_file: Path) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    if not config_file.exists():
        print_message(Colors.RED, f"ERROR: Config file not found: {config_file}")
        sys.exit(1)

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Validate required sections
        required_sections = ["network", "common", "hosts"]
        for section in required_sections:
            if section not in config:
                print_message(
                    Colors.RED, f"ERROR: Missing '{section}' section in config file"
                )
                sys.exit(1)

        # Convert hosts list to dict for easier access
        hosts_dict = {}
        for host in config["hosts"]:
            hosts_dict[host["number"]] = host

        config["hosts_dict"] = hosts_dict
        return config

    except yaml.YAMLError as e:
        print_message(Colors.RED, f"ERROR: Failed to parse YAML config: {e}")
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
            print_message(Colors.GREEN, "✓ Valid ISO file found")
            return True
        else:
            print_message(Colors.RED, "ERROR: File is not a valid ISO image")
            return False
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_message(Colors.YELLOW, "Warning: Could not verify ISO format")
        return True  # Assume valid if file command fails


def validate_disk_selection(device: str) -> bool:
    """Validate disk selection with safety checks"""
    # Prevent selecting disk0
    if "disk0" in device:
        print_message(
            Colors.RED, "FATAL ERROR: Cannot select disk0 (internal system disk)!"
        )
        print_message(
            Colors.YELLOW, "Selecting disk0 would erase your macOS installation!"
        )
        return False

    # Check if disk exists
    if not Path(device).exists():
        print_message(Colors.RED, f"ERROR: Device {device} does not exist")
        print("Run 'diskutil list' to see available devices")
        return False

    return True


class ReFindUSBCreator:
    """Create rEFInd UEFI boot menu USB for multiple ESXi hosts"""

    # rEFInd download URL (version 0.14.2)
    REFIND_URL = "https://sourceforge.net/projects/refind/files/0.14.2/refind-bin-0.14.2.zip/download"
    REFIND_VERSION = "0.14.2"

    def __init__(self, config: Dict[str, Any], config_dir: Path):
        self.config = config
        self.config_dir = config_dir

    def create_usb(
        self,
        usb_device: str,
        iso_path: str,
        usb_label: str = "VCF",
        skip_confirm: bool = False,
        dry_run: bool = False,
    ):
        """Create rEFInd USB boot menu"""

        if dry_run:
            print_message(Colors.YELLOW, "========================================")
            print_message(Colors.YELLOW, "DRY RUN MODE - No changes will be made")
            print_message(Colors.YELLOW, "========================================\n")

        # Verify ISO exists
        if not Path(iso_path).exists():
            if dry_run:
                print_message(
                    Colors.YELLOW, f"⚠ ESXi ISO not found (would fail): {iso_path}"
                )
            else:
                print_message(Colors.RED, f"ERROR: ESXi ISO not found at: {iso_path}")
                sys.exit(1)
        else:
            print_message(Colors.GREEN, f"✓ Found ESXi ISO: {iso_path}")

        # Verify kickstart configs exist
        missing_configs = []
        for host_num in sorted(self.config["hosts_dict"].keys()):
            kickstart_file = self.config_dir / f"ks-esx0{host_num}.cfg"
            if not kickstart_file.exists():
                missing_configs.append(str(kickstart_file))

        if missing_configs:
            if dry_run:
                print_message(
                    Colors.YELLOW, f"⚠ Kickstart configs not found (would fail):"
                )
                for cfg in missing_configs:
                    print(f"    - {cfg}")
            else:
                print_message(Colors.RED, "ERROR: Kickstart configs not found:")
                for cfg in missing_configs:
                    print(f"    - {cfg}")
                print("\nRun 'make generate' first to generate kickstart configs")
                sys.exit(1)
        else:
            print_message(
                Colors.GREEN,
                f"✓ Found {len(self.config['hosts_dict'])} kickstart configs",
            )

        # Validate USB device
        if not dry_run:
            if not validate_disk_selection(usb_device):
                sys.exit(1)

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
            print(f"  USB Label:      {usb_label}")
            print(f"  ESXi ISO:       {iso_path}")
            print(f"  Hosts:          {len(self.config['hosts_dict'])}")
            for host_num in sorted(self.config["hosts_dict"].keys()):
                host = self.config["hosts_dict"][host_num]
                print(f"    - Host {host_num}: {host['hostname']} ({host['ip']})")
            print()
            response = input("Type 'yes' to continue: ")
            if response.lower() != "yes":
                print_message(Colors.RED, "Operation cancelled by user")
                sys.exit(1)

        # Display operation plan
        print()
        print(f"{Colors.BLUE}Operation Plan:{Colors.NC}")
        print(f"  USB Device:     {usb_device}")
        print(f"  USB Label:      {usb_label}")
        print(f"  ESXi ISO:       {Path(iso_path).name}")
        print(f"  Hosts:          {len(self.config['hosts_dict'])}")
        print(f"  Boot Menu:      rEFInd {self.REFIND_VERSION}")
        print()

        if dry_run:
            self._dry_run_steps(usb_device, usb_label, iso_path)
        else:
            self._execute_steps(usb_device, usb_label, iso_path)

    def _dry_run_steps(self, usb_device: str, usb_label: str, iso_path: str):
        """Show what would be done in dry-run mode"""
        print(f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would unmount USB device")
        print(
            f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would partition as FAT32 (label: {usb_label})"
        )
        print(f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would create directory structure:")
        print(f"  - /Volumes/{usb_label}/EFI/BOOT/")
        print(f"  - /Volumes/{usb_label}/esx9/")
        print(f"  - /Volumes/{usb_label}/kickstart/")
        print(f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would extract ISO contents to /esx9/")
        print(f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would modify main BOOT.CFG")
        print(f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would create host-specific BOOT directories:")
        for host_num in sorted(self.config["hosts_dict"].keys()):
            print(f"  - /Volumes/{usb_label}/esx9/ks{host_num}/BOOT/")
        print(f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would copy kickstart files")
        print(
            f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would download rEFInd {self.REFIND_VERSION}"
        )
        print(
            f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would create rEFInd menu with {len(self.config['hosts_dict'])} entries"
        )
        print(f"{Colors.BLUE}[DRY RUN]{Colors.NC} Would eject USB")

        print()
        print(f"{Colors.GREEN}========================================{Colors.NC}")
        print(f"{Colors.YELLOW}DRY RUN Complete - No changes made{Colors.NC}")
        print(f"{Colors.GREEN}========================================{Colors.NC}")

    def _execute_steps(self, usb_device: str, usb_label: str, iso_path: str):
        """Execute the actual USB creation steps"""

        # Step 1: Partition USB as FAT32
        print_message(Colors.YELLOW, "Step 1/9: Partitioning USB as FAT32...")
        try:
            subprocess.run(
                ["diskutil", "unmountDisk", usb_device],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            subprocess.run(
                [
                    "diskutil",
                    "partitionDisk",
                    usb_device,
                    "1",
                    "MBRFormat",
                    "MS-DOS",
                    usb_label,
                    "R",
                ],
                check=True,
            )
            print_message(
                Colors.GREEN, f"✓ USB partitioned as FAT32 (label: {usb_label})"
            )
        except subprocess.CalledProcessError:
            print_message(Colors.RED, "ERROR: Failed to partition USB")
            sys.exit(1)

        usb_mount = Path(f"/Volumes/{usb_label}")
        time.sleep(2)  # Wait for mount

        if not usb_mount.exists():
            print_message(Colors.RED, f"ERROR: USB not mounted at {usb_mount}")
            sys.exit(1)

        # Step 2: Create directory structure
        print_message(Colors.YELLOW, "Step 2/9: Creating directory structure...")
        try:
            (usb_mount / "EFI" / "BOOT").mkdir(parents=True, exist_ok=True)
            (usb_mount / "esx9").mkdir(parents=True, exist_ok=True)
            (usb_mount / "kickstart").mkdir(parents=True, exist_ok=True)
            print_message(Colors.GREEN, "✓ Directory structure created")
        except Exception as e:
            print_message(Colors.RED, f"ERROR: Failed to create directories: {e}")
            sys.exit(1)

        # Step 3: Extract ISO contents
        print_message(
            Colors.YELLOW,
            "Step 3/9: Extracting ESXi ISO contents (this may take 5-10 minutes)...",
        )
        iso_mount = self._mount_iso(iso_path)
        try:
            start_time = time.time()
            subprocess.run(
                ["cp", "-R", f"{iso_mount}/", f"{usb_mount / 'esx9'}/"],
                check=False,
                stderr=subprocess.DEVNULL,
            )
            duration = int(time.time() - start_time)
            print_message(Colors.GREEN, f"✓ ISO contents extracted (took {duration}s)")
        except Exception as e:
            print_message(Colors.RED, f"ERROR: Failed to extract ISO: {e}")
            self._unmount_iso(iso_mount)
            sys.exit(1)
        finally:
            self._unmount_iso(iso_mount)

        # Step 4: Modify main BOOT.CFG
        print_message(Colors.YELLOW, "Step 4/9: Modifying BOOT.CFG...")
        self._modify_boot_cfg(usb_mount / "esx9" / "EFI" / "BOOT" / "BOOT.CFG")

        # Step 5: Create ks1, ks2, ks3 directories with BOOT copies
        print_message(Colors.YELLOW, "Step 5/9: Creating per-host BOOT directories...")
        self._create_host_boot_dirs(usb_mount / "esx9")

        # Step 6: Copy kickstart files
        print_message(Colors.YELLOW, "Step 6/9: Copying kickstart files...")
        self._copy_kickstart_files(usb_mount / "kickstart")

        # Step 7: Download and extract rEFInd
        print_message(
            Colors.YELLOW, f"Step 7/9: Downloading rEFInd {self.REFIND_VERSION}..."
        )
        refind_binary = self._download_refind()

        # Step 8: Install rEFInd bootloader
        print_message(Colors.YELLOW, "Step 8/9: Installing rEFInd bootloader...")
        try:
            shutil.copy(refind_binary, usb_mount / "EFI" / "BOOT" / "bootx64.efi")
            print_message(Colors.GREEN, "✓ rEFInd bootloader installed")
        except Exception as e:
            print_message(Colors.RED, f"ERROR: Failed to install rEFInd: {e}")
            sys.exit(1)

        # Step 9: Create rEFInd configuration
        print_message(Colors.YELLOW, "Step 9/9: Creating rEFInd boot menu...")
        self._create_refind_config(usb_mount / "EFI" / "BOOT" / "refind.conf")

        # Eject USB
        print_message(Colors.YELLOW, "Ejecting USB device...")
        subprocess.run(["sync"], check=False)
        subprocess.run(["diskutil", "eject", usb_device], check=False)
        print_message(Colors.GREEN, "✓ USB device ejected")

        # Print summary
        self._print_summary(usb_device, usb_label)

    def _mount_iso(self, iso_path: str) -> Path:
        """Mount ISO and return mount point"""
        iso_mount = Path(tempfile.mkdtemp(prefix="esxi-iso-"))
        try:
            subprocess.run(
                [
                    "hdiutil",
                    "attach",
                    iso_path,
                    "-mountpoint",
                    str(iso_mount),
                    "-readonly",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            return iso_mount
        except subprocess.CalledProcessError:
            print_message(Colors.RED, "ERROR: Failed to mount ISO")
            iso_mount.rmdir()
            sys.exit(1)

    def _unmount_iso(self, iso_mount: Path):
        """Unmount ISO and cleanup"""
        subprocess.run(
            ["hdiutil", "detach", str(iso_mount)],
            check=False,
            stderr=subprocess.DEVNULL,
        )
        try:
            iso_mount.rmdir()
        except:
            pass

    def _modify_boot_cfg(self, boot_cfg_path: Path):
        """Modify BOOT.CFG to update prefix and remove leading slashes from modules"""
        if not boot_cfg_path.exists():
            print_message(Colors.RED, f"ERROR: BOOT.CFG not found at: {boot_cfg_path}")
            sys.exit(1)

        try:
            # Backup original
            shutil.copy(boot_cfg_path, f"{boot_cfg_path}.backup")

            # Read and modify
            content = boot_cfg_path.read_text()
            new_content = []

            for line in content.splitlines():
                if line.startswith("prefix="):
                    # Update prefix to /esx9/
                    new_content.append("prefix=/esx9/")
                elif line.startswith("kernel="):
                    # Remove leading slash from kernel path
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        kernel_path = parts[1].lstrip("/")
                        new_content.append(f"kernel={kernel_path}")
                    else:
                        new_content.append(line)
                elif line.startswith("modules="):
                    # Remove leading slashes from module names
                    # Split by --- and process each module
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        modules = parts[1]
                        # Remove leading / from each module name
                        modules = re.sub(r"(^| )/+", r"\1", modules)
                        new_content.append(f"modules={modules}")
                    else:
                        new_content.append(line)
                else:
                    new_content.append(line)

            boot_cfg_path.write_text("\n".join(new_content) + "\n")
            print_message(
                Colors.GREEN, "✓ BOOT.CFG modified (prefix=/esx9/, kernel/module slashes removed)"
            )

        except Exception as e:
            print_message(Colors.RED, f"ERROR: Failed to modify BOOT.CFG: {e}")
            sys.exit(1)

    def _create_host_boot_dirs(self, esx9_dir: Path):
        """Create ks1, ks2, ks3 directories with copies of BOOT directory and modified BOOT.CFG"""
        try:
            source_boot_dir = esx9_dir / "EFI" / "BOOT"

            for host_num in sorted(self.config["hosts_dict"].keys()):
                # Create ksX/BOOT directory
                ks_boot_dir = esx9_dir / f"ks{host_num}" / "BOOT"
                ks_boot_dir.mkdir(parents=True, exist_ok=True)

                # Copy all files from source BOOT directory
                for file in source_boot_dir.iterdir():
                    if file.is_file():
                        shutil.copy(file, ks_boot_dir / file.name)

                # Modify BOOT.CFG to add kickstart parameter
                boot_cfg = ks_boot_dir / "BOOT.CFG"
                if boot_cfg.exists():
                    content = boot_cfg.read_text()
                    new_content = []

                    for line in content.splitlines():
                        if line.startswith("kernelopt="):
                            # Add kickstart parameter
                            new_content.append(f"kernelopt=ks=usb:/kickstart/KS-ESX0{host_num}.CFG")
                        else:
                            new_content.append(line)

                    boot_cfg.write_text("\n".join(new_content) + "\n")

            print_message(
                Colors.GREEN,
                f"✓ Created {len(self.config['hosts_dict'])} host-specific BOOT directories",
            )
        except Exception as e:
            print_message(Colors.RED, f"ERROR: Failed to create host BOOT directories: {e}")
            sys.exit(1)

    def _copy_kickstart_files(self, kickstart_dir: Path):
        """Copy kickstart files to USB with capitalized filenames"""
        try:
            for host_num in sorted(self.config["hosts_dict"].keys()):
                source = self.config_dir / f"ks-esx0{host_num}.cfg"
                # Capitalize filename: KS-ESX01.CFG
                dest = kickstart_dir / f"KS-ESX0{host_num}.CFG"
                shutil.copy(source, dest)

            print_message(
                Colors.GREEN,
                f"✓ Copied {len(self.config['hosts_dict'])} kickstart files",
            )
        except Exception as e:
            print_message(Colors.RED, f"ERROR: Failed to copy kickstart files: {e}")
            sys.exit(1)

    def _download_refind(self) -> Path:
        """Download and extract rEFInd bootloader, return path to refind_x64.efi"""
        try:
            import urllib.request
            import zipfile

            temp_dir = Path(tempfile.mkdtemp(prefix="refind-"))
            zip_path = temp_dir / "refind.zip"

            # Download
            print(f"  Downloading from SourceForge...")
            urllib.request.urlretrieve(self.REFIND_URL, zip_path)

            # Extract
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            # Find refind_x64.efi
            refind_binary = (
                temp_dir
                / f"refind-bin-{self.REFIND_VERSION}"
                / "refind"
                / "refind_x64.efi"
            )

            if not refind_binary.exists():
                print_message(
                    Colors.RED, "ERROR: refind_x64.efi not found in downloaded package"
                )
                sys.exit(1)

            print_message(Colors.GREEN, f"✓ rEFInd {self.REFIND_VERSION} downloaded")
            return refind_binary

        except Exception as e:
            print_message(Colors.RED, f"ERROR: Failed to download rEFInd: {e}")
            sys.exit(1)

    def _create_refind_config(self, config_path: Path):
        """Create rEFInd configuration file with menu entries"""
        try:
            config_lines = [
                "# rEFInd Boot Menu Configuration",
                "# Auto-generated by create_refind_usb.py",
                "",
                "timeout 40",
                "textonly",
                "scanfor manual",
                "showtools shell, reboot",
                "",
            ]

            # Add menu entry for each host
            for host_num in sorted(self.config["hosts_dict"].keys()):
                host = self.config["hosts_dict"][host_num]
                config_lines.extend(
                    [
                        f'menuentry "ESXi 9.0 - {host["hostname"]}" {{',
                        f"    loader /esx9/ks{host_num}/BOOT/BOOTX64.EFI",
                        "}",
                        "",
                    ]
                )

            config_path.write_text("\n".join(config_lines))
            print_message(
                Colors.GREEN,
                f"✓ rEFInd menu created with {len(self.config['hosts_dict'])} entries",
            )

        except Exception as e:
            print_message(Colors.RED, f"ERROR: Failed to create rEFInd config: {e}")
            sys.exit(1)

    def _print_summary(self, usb_device: str, usb_label: str):
        """Print completion summary with next steps"""
        print(f"\n{Colors.GREEN}========================================{Colors.NC}")
        print(f"{Colors.GREEN}rEFInd USB Creation Complete!{Colors.NC}")
        print(f"{Colors.GREEN}========================================{Colors.NC}\n")

        print(f"USB Device:    {usb_device}")
        print(f"USB Label:     {usb_label}")
        print(f"Boot Menu:     rEFInd {self.REFIND_VERSION}")
        print(f"Menu Entries:  {len(self.config['hosts_dict'])}")
        print()

        print("Boot Menu Options:")
        for host_num in sorted(self.config["hosts_dict"].keys()):
            host = self.config["hosts_dict"][host_num]
            print(f"  {host_num}. ESXi 9.0 - {host['hostname']} ({host['ip']})")

        print()
        print_message(Colors.YELLOW, "Next Steps:")
        print("1. Remove USB drive from computer")
        print("2. Insert USB into any MS-A2 host")
        print("3. Power on and select USB boot (F11/F12)")
        print("4. rEFInd menu will appear - select the desired host")
        print("5. Installation will proceed automatically with kickstart")
        print("6. Reuse same USB for all hosts!")
        print()
        print_message(Colors.GREEN, "Benefits:")
        print("  ✓ Single USB for all hosts")
        print("  ✓ No need to modify USB between hosts")
        print("  ✓ Visual boot menu with host selection")
        print("  ✓ Each host gets correct kickstart config")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Create rEFInd UEFI boot menu USB for multiple ESXi hosts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run /dev/disk4                    # Dry run (no root required)
  sudo %(prog)s /dev/disk4                         # Create rEFInd USB
  sudo %(prog)s /dev/disk4 --label ESXI            # Custom USB label
  sudo %(prog)s /dev/disk4 -y                      # Skip confirmations

This script creates a single USB drive with rEFInd boot menu that allows
you to select which ESXi host to install, using the appropriate kickstart
configuration for each host.

Based on: https://williamlam.com/2025/07/custom-uefi-boot-menu-for-esxi-9-0-using-refind.html
        """,
    )

    parser.add_argument(
        "usb_device", nargs="?", help="USB device path (e.g., /dev/disk4)"
    )

    parser.add_argument("-i", "--iso", type=Path, help="Path to ESXi ISO file")

    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="Path to YAML config file (default: config/vcf-config.yaml)",
    )

    parser.add_argument(
        "-l", "--label", type=str, default="VCF", help="USB volume label (default: VCF)"
    )

    parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompts"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making any changes",
    )

    args = parser.parse_args()

    # Validate required arguments
    if not args.usb_device:
        print_message(Colors.RED, "ERROR: Missing USB device argument")
        parser.print_help()
        sys.exit(1)

    # Check macOS
    check_macos()

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
        print_message(Colors.RED, "ERROR: ESXi ISO path not specified")
        print("Please specify the ESXi ISO path using one of these methods:")
        print("1. Use the -i/--iso command line option:")
        print(
            "   Example: sudo uv run scripts/create_refind_usb.py /dev/disk4 -i /path/to/esxi.iso"
        )
        print("2. Add 'esxi_iso_path' to the 'common' section in your config file")
        sys.exit(1)

    # Validate ISO
    print(f"ISO: {Path(iso_path).name}")
    if not validate_iso(iso_path):
        sys.exit(1)

    # Print header
    print(f"\n{Colors.GREEN}========================================{Colors.NC}")
    print(f"{Colors.GREEN}rEFInd USB Boot Menu Creator{Colors.NC}")
    print(f"{Colors.GREEN}========================================{Colors.NC}\n")

    # Create USB
    creator = ReFindUSBCreator(config, config_dir)
    try:
        creator.create_usb(
            args.usb_device, iso_path, args.label, args.yes, args.dry_run
        )
    except KeyboardInterrupt:
        print()
        print_message(Colors.YELLOW, "Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_message(Colors.RED, f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
