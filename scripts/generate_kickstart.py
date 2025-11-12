#!/usr/bin/env python3
"""
ESXi Kickstart Config Generator
Purpose: Generate ESXi kickstart configs from Jinja2 template
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader

# Add scripts directory to path for vcf_secrets import
sys.path.insert(0, str(Path(__file__).parent))

# pylint: disable=wrong-import-position
from vcf_secrets import load_config_with_secrets


# Color output
# pylint: disable=too-few-public-methods
class Colors:
    """ANSI color codes for terminal output"""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color


def load_config(config_file: Path) -> Dict[str, Any]:
    """Load configuration from YAML file with secrets"""
    # Load config with secrets (handles passwords from env/secrets file)
    config = load_config_with_secrets(config_file)

    # Convert hosts list to dict for easier access
    hosts_dict = {}
    for host in config["hosts"]:
        hosts_dict[host["number"]] = host

    config["hosts_dict"] = hosts_dict
    return config


class KickstartGenerator:
    """Generate ESXi kickstart configs from Jinja2 template"""

    def __init__(self, script_dir: Path, config: Dict[str, Any]):
        self.script_dir = script_dir
        self.project_dir = script_dir.parent
        self.config_dir = self.project_dir / "config"
        self.template_file = self.config_dir / "ks-template.cfg.j2"
        self.config = config

        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.config_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def get_template_vars(self, host_num: int) -> Dict[str, str]:
        """Get template variables for a specific host"""
        host_config = self.config["hosts_dict"][host_num]
        network = self.config["network"]
        common = self.config["common"]

        return {
            # Network settings
            "vlan_id": network["vlan_id"],
            "vmnic": network["vmnic"],
            "host_ip": host_config["ip"],
            "netmask": network["netmask"],
            "gateway": network["gateway"],
            "hostname": host_config["hostname"],
            "dns_server": network["dns_server"],
            "ntp_server": common["ntp_server"],
            "vswitch_mtu": network["vswitch_mtu"],
            # Host-specific settings
            "install_disk": host_config["install_disk"],
            "tiering_disk": host_config["tiering_disk"],
            "datastore_name": host_config["datastore_name"],
            # Security settings
            "root_password": common["root_password"],
            "ssh_key": common["ssh_root_key"],
            # Deployment settings
            "host_count": len(self.config["hosts_dict"]),
        }

    def generate_kickstart(self, host_num: int, output_dir: Path) -> Path:
        """Generate kickstart config for a specific host"""
        output_file = output_dir / f"ks-esx0{host_num}.cfg"

        print(f"{Colors.YELLOW}Generating kickstart for ESX0{host_num}...{Colors.NC}")

        # Check if template exists
        if not self.template_file.exists():
            print(
                f"{Colors.RED}ERROR: Template file not found: {self.template_file}{Colors.NC}"
            )
            sys.exit(1)

        # Get template variables
        template_vars = self.get_template_vars(host_num)

        # Load and render template
        template = self.env.get_template(self.template_file.name)
        rendered = template.render(**template_vars)

        # Write output file
        output_file.write_text(rendered)

        print(f"{Colors.GREEN}✓{Colors.NC} Created: {output_file}")
        print(f"{Colors.BLUE}  IP:        {template_vars['host_ip']}{Colors.NC}")
        print(f"{Colors.BLUE}  Hostname:  {template_vars['hostname']}{Colors.NC}")
        print(f"{Colors.BLUE}  Datastore: {template_vars['datastore_name']}{Colors.NC}")

        return output_file

    def generate_all(self, output_dir: Path) -> List[Path]:
        """Generate kickstart configs for all hosts"""
        host_count = len(self.config["hosts_dict"])
        print(f"Generating kickstart configs for {host_count} host(s)...\n")

        output_files = []
        for host_num in sorted(self.config["hosts_dict"].keys()):
            output_files.append(self.generate_kickstart(host_num, output_dir))
            print()

        return output_files


def main():
    parser = argparse.ArgumentParser(
        description="Generate ESXi kickstart configs from Jinja2 template",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Generate all configs to config/
  %(prog)s 1                        # Generate only esx01 config
  %(prog)s all                      # Generate all configs
  %(prog)s 3 /tmp                   # Generate esx03 config to /tmp
  %(prog)s --config myconfig.yaml   # Use custom config file
        """,
    )

    parser.add_argument(
        "host",
        nargs="?",
        default="all",
        help="Host number (1, 2, 3) or 'all' (default: all)",
    )

    parser.add_argument(
        "output_dir", nargs="?", type=Path, help="Output directory (default: config/)"
    )

    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="Path to YAML config file (default: config/vcf-config.yaml)",
    )

    args = parser.parse_args()

    # Determine script and output directories
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent
    output_dir = args.output_dir if args.output_dir else project_dir / "config"

    # Determine config file
    config_file = (
        args.config if args.config else project_dir / "config" / "vcf-config.yaml"
    )

    # Load configuration
    config = load_config(config_file)

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create generator
    generator = KickstartGenerator(script_dir, config)

    # Print header
    print(f"{Colors.GREEN}========================================{Colors.NC}")
    print(f"{Colors.GREEN}ESXi Kickstart Config Generator{Colors.NC}")
    print(f"{Colors.GREEN}========================================{Colors.NC}\n")

    # Generate configs
    if args.host == "all":
        output_files = generator.generate_all(output_dir)

        print(f"{Colors.GREEN}========================================{Colors.NC}")
        print(f"{Colors.GREEN}Generation Complete!{Colors.NC}")
        print(f"{Colors.GREEN}========================================{Colors.NC}\n")

        print(f"Generated files in {Colors.YELLOW}{output_dir}/{Colors.NC}:")
        for host_num in sorted(config["hosts_dict"].keys()):
            host = config["hosts_dict"][host_num]
            print(f"  - ks-esx0{host_num}.cfg ({host['ip']}) - {host['hostname']}")
        print()

        print(f"{Colors.YELLOW}⚠ IMPORTANT:{Colors.NC}")
        print("  Review the generated configs, especially:")
        print("  - NVMe device identifiers (run 'vdq -q' on ESXi console)")
        print("  - Network settings (IP, VLAN, gateway, DNS)")
        print("  - Root password")
        print()
    else:
        # Validate host number
        try:
            host_num = int(args.host)
            if host_num not in config["hosts_dict"]:
                print(
                    f"{Colors.RED}ERROR: Host {host_num} not found in config file{Colors.NC}"
                )
                sys.exit(1)
        except ValueError:
            print(f"{Colors.RED}ERROR: Invalid host number: {args.host}{Colors.NC}")
            sys.exit(1)

        generator.generate_kickstart(host_num, output_dir)
        print()
        print(f"{Colors.GREEN}✓ Generation complete!{Colors.NC}")
        print()

    # Print configuration summary
    print(f"{Colors.BLUE}Configuration:{Colors.NC}")
    print(f"  Config File: {config_file}")
    print(f"  Network:     {config['network']['subnet']}")
    print(f"  Gateway:     {config['network']['gateway']}")
    print(f"  VLAN:        {config['network']['vlan_id']}")
    print(f"  DNS:         {config['network']['dns_server']}")
    print(f"  NTP:         {config['common']['ntp_server']}")
    print()


if __name__ == "__main__":
    main()
