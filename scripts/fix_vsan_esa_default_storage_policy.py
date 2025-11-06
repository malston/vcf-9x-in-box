#!/usr/bin/env python3
"""
vSAN ESA Storage Policy Fix Script
Purpose: Fix vSAN ESA default storage policy for 2-node deployments
Author: Modernized from William Lam's PowerShell script

IMPORTANT: This script is ONLY needed for 2-node VCF deployments.
For 3+ node deployments, the default policy is correct (FTT=1).
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional
import urllib3

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml module not found. Install with: uv sync")
    sys.exit(1)

try:
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim, pbm
    from pyVim import sso
except ImportError:
    print("ERROR: pyvmomi module not found. Install with: uv sync")
    sys.exit(1)

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# Color output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


def load_config(config_file: Path) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    if not config_file.exists():
        print(f"{Colors.RED}ERROR: Config file not found: {config_file}{Colors.NC}")
        sys.exit(1)

    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        # Validate required sections
        required_sections = ['vcenter', 'hosts']
        for section in required_sections:
            if section not in config:
                print(f"{Colors.RED}ERROR: Missing '{section}' section in config file{Colors.NC}")
                sys.exit(1)

        return config

    except yaml.YAMLError as e:
        print(f"{Colors.RED}ERROR: Failed to parse YAML config: {e}{Colors.NC}")
        sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}ERROR: Failed to load config: {e}{Colors.NC}")
        sys.exit(1)


class VSANPolicyFixer:
    """Fix vSAN ESA default storage policy for 2-node deployments"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.vcenter = config['vcenter']
        self.host_count = len(config['hosts'])

        self.si: Optional[vim.ServiceInstance] = None
        self.pbm_si: Optional[pbm.ServiceInstance] = None

    def wait_for_ping(self, timeout: int = 1800) -> bool:
        """Wait for vCenter to be pingable"""
        interval = 900  # 15 minutes
        elapsed = 0

        print(f"{Colors.YELLOW}⏳ Checking if vCenter ({self.vcenter['hostname']}) is pingable...{Colors.NC}")

        while elapsed < timeout:
            try:
                # Use subprocess to ping
                result = subprocess.run(
                    ['ping', '-c', '1', self.vcenter['hostname']],
                    capture_output=True,
                    timeout=5
                )

                if result.returncode == 0:
                    print(f"{Colors.GREEN}✓ vCenter is pingable!{Colors.NC}\n")
                    return True

            except Exception:
                pass

            if elapsed > 0:
                print(f"{Colors.YELLOW}⏳ vCenter not pingable yet. "
                      f"Sleeping for {interval // 60} minutes... "
                      f"(elapsed: {elapsed // 60}/{timeout // 60} min){Colors.NC}")
            time.sleep(interval)
            elapsed += interval

        print(f"{Colors.RED}ERROR: Timeout waiting for vCenter to be pingable{Colors.NC}")
        return False

    def wait_for_vcenter_connection(self, timeout: int = 1800) -> bool:
        """Wait for vCenter to accept connections"""
        interval = 600  # 10 minutes
        elapsed = 0

        print(f"{Colors.YELLOW}⏳ Waiting for vCenter to accept connections...{Colors.NC}")

        while elapsed < timeout:
            try:
                self.si = SmartConnect(
                    host=self.vcenter['hostname'],
                    user=self.vcenter['username'],
                    pwd=self.vcenter['password'],
                    disableSslCertValidation=True
                )

                print(f"{Colors.GREEN}✓ Connected to vCenter!{Colors.NC}\n")
                return True

            except Exception as e:
                if elapsed > 0:
                    print(f"{Colors.YELLOW}⏳ vCenter not ready for login yet. "
                          f"Sleeping for {interval // 60} minutes... "
                          f"(elapsed: {elapsed // 60}/{timeout // 60} min){Colors.NC}")
                time.sleep(interval)
                elapsed += interval

        print(f"{Colors.RED}ERROR: Timeout waiting for vCenter connection{Colors.NC}")
        return False

    def wait_for_vcf_policy(self, timeout: int = 1800) -> bool:
        """Wait for VCF storage policy to be available"""
        interval = 60  # 1 minute
        elapsed = 0

        print(f"{Colors.YELLOW}⏳ Waiting for VCF Storage Policy to be available...{Colors.NC}")

        while elapsed < timeout:
            try:
                # Connect to SPBM (Storage Policy Based Management)
                pbm_stub = self._connect_spbm()
                if not pbm_stub:
                    raise Exception("Failed to connect to SPBM")

                # Get storage policies
                pm = pbm_stub.RetrieveContent().profileManager
                profile_ids = pm.PbmQueryProfile(
                    resourceType=pbm.profile.ResourceType(
                        resourceType='STORAGE'
                    )
                )

                # Find VCF policy
                if profile_ids:
                    profiles = pm.PbmRetrieveContent(profileIds=profile_ids)
                    for profile in profiles:
                        if 'VCF' in profile.name:
                            print(f"{Colors.GREEN}✓ VCF Storage Policy found: {profile.name}{Colors.NC}\n")
                            self.pbm_si = pbm_stub
                            return True

            except Exception as e:
                pass

            if elapsed > 0:
                print(f"{Colors.YELLOW}⏳ VCF Storage Policy not found yet. "
                      f"Sleeping for {interval // 60} minute(s)... "
                      f"(elapsed: {elapsed // 60}/{timeout // 60} min){Colors.NC}")
            time.sleep(interval)
            elapsed += interval

        print(f"{Colors.RED}ERROR: Timeout waiting for VCF Storage Policy{Colors.NC}")
        return False

    def _connect_spbm(self):
        """Connect to Storage Policy Based Management service"""
        try:
            # Get session cookie from vCenter connection
            session_cookie = self.si._stub.cookie.split('"')[1]

            # Create SPBM stub
            context = None
            if hasattr(vim, 'GetHttpsContext'):
                context = vim.GetHttpsContext()

            hostname = self.vcenter['hostname']
            pbm_stub = pbm.VmomiSupport.GetStub(
                'pbm',
                host=hostname,
                sslContext=context,
                connectionPoolTimeout=0
            )

            # Set the session cookie
            pbm_stub.cookie = f'"{session_cookie}"'

            return pbm_stub

        except Exception as e:
            print(f"{Colors.RED}ERROR: Failed to connect to SPBM: {e}{Colors.NC}")
            return None

    def fix_storage_policy(self, dry_run: bool = False) -> bool:
        """Fix vSAN storage policy (set FTT to 0 for 2-node)"""
        try:
            print(f"{Colors.YELLOW}Updating VCF Storage Policy...{Colors.NC}")

            if dry_run:
                print(f"{Colors.YELLOW}DRY RUN: Would update VCF Storage Policy FTT from 1 to 0{Colors.NC}\n")
                return True

            # Get profile manager
            pm = self.pbm_si.RetrieveContent().profileManager

            # Get all storage profiles
            profile_ids = pm.PbmQueryProfile(
                resourceType=pbm.profile.ResourceType(
                    resourceType='STORAGE'
                )
            )

            # Find VCF policy
            vcf_profile = None
            if profile_ids:
                profiles = pm.PbmRetrieveContent(profileIds=profile_ids)
                for profile in profiles:
                    if 'VCF' in profile.name:
                        vcf_profile = profile
                        break

            if not vcf_profile:
                print(f"{Colors.RED}ERROR: VCF Storage Policy not found{Colors.NC}")
                return False

            print(f"{Colors.BLUE}Found policy: {vcf_profile.name}{Colors.NC}")

            # Create new capability with FTT=0
            # Note: The capability name for VSAN is 'VSAN.hostFailuresToTolerate'
            capability = pbm.capability.CapabilityInstance(
                id=pbm.capability.CapabilityMetadata.UniqueId(
                    namespace='VSAN',
                    id='hostFailuresToTolerate'
                ),
                constraint=[
                    pbm.capability.ConstraintInstance(
                        propertyInstance=[
                            pbm.capability.PropertyInstance(
                                id='hostFailuresToTolerate',
                                value=0
                            )
                        ]
                    )
                ]
            )

            # Create rule set
            rule = pbm.capability.Rule(
                capabilityId=capability.id,
                constraint=[capability.constraint[0]]
            )

            rule_set = pbm.capability.RuleSet(
                rule=[rule]
            )

            # Update the profile
            spec = pbm.profile.CapabilityBasedProfileUpdateSpec(
                constraints=pbm.profile.SubProfileCapabilityConstraints(
                    subProfiles=[
                        pbm.profile.SubProfileCapabilityConstraints.SubProfile(
                            name='VSAN',
                            capability=[capability]
                        )
                    ]
                )
            )

            # Update the profile
            pm.PbmUpdate(
                profileId=vcf_profile.profileId,
                updateSpec=spec
            )

            print(f"{Colors.GREEN}✓ VCF Storage Policy updated successfully (FTT: 1 → 0){Colors.NC}\n")
            return True

        except Exception as e:
            print(f"{Colors.RED}ERROR: Failed to update storage policy: {e}{Colors.NC}")
            import traceback
            traceback.print_exc()
            return False

    def disconnect(self):
        """Disconnect from vCenter"""
        if self.si:
            try:
                Disconnect(self.si)
                print(f"{Colors.GREEN}✓ Disconnected from vCenter{Colors.NC}\n")
            except Exception:
                pass

    def run(self, dry_run: bool = False, skip_wait: bool = False) -> bool:
        """Run the storage policy fix"""
        print(f"{Colors.GREEN}========================================{Colors.NC}")
        print(f"{Colors.GREEN}vSAN ESA Storage Policy Fix{Colors.NC}")
        print(f"{Colors.GREEN}========================================{Colors.NC}\n")

        # Check if this is needed
        if self.host_count >= 3:
            print(f"{Colors.YELLOW}⚠ WARNING: This script is only needed for 2-node deployments{Colors.NC}")
            print(f"{Colors.BLUE}Your configuration has {self.host_count} hosts.{Colors.NC}")
            print(f"{Colors.BLUE}The default vSAN policy (FTT=1) is correct for 3+ node deployments.{Colors.NC}\n")
            print(f"{Colors.YELLOW}Skipping policy fix.{Colors.NC}\n")
            return True

        if dry_run:
            print(f"{Colors.YELLOW}DRY RUN MODE - No changes will be made{Colors.NC}\n")

        print(f"{Colors.BLUE}Configuration:{Colors.NC}")
        print(f"  vCenter:    {self.vcenter['hostname']}")
        print(f"  Host Count: {self.host_count}")
        print(f"  Policy Fix: FTT 1 → 0 (required for 2-node vSAN ESA)")
        print()

        if not skip_wait:
            # Wait for vCenter to be ready
            if not self.wait_for_ping():
                return False

        # Connect to vCenter
        if not self.wait_for_vcenter_connection():
            return False

        # Wait for VCF policy to be available
        if not self.wait_for_vcf_policy():
            self.disconnect()
            return False

        # Fix the storage policy
        success = self.fix_storage_policy(dry_run)

        # Disconnect
        self.disconnect()

        if success:
            print(f"{Colors.GREEN}========================================{Colors.NC}")
            print(f"{Colors.GREEN}Storage Policy Fix Complete!{Colors.NC}")
            print(f"{Colors.GREEN}========================================{Colors.NC}\n")

            print(f"{Colors.BLUE}Next Steps:{Colors.NC}")
            print(f"  - VCF deployment should continue normally")
            print(f"  - Monitor deployment progress in VCF Installer UI")
            print()

        return success


def main():
    parser = argparse.ArgumentParser(
        description="Fix vSAN ESA default storage policy for 2-node deployments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Wait for vCenter and fix policy
  %(prog)s --dry-run                # Preview changes without executing
  %(prog)s --skip-wait              # Skip waiting for vCenter (if already ready)
  %(prog)s --config custom.yaml    # Use custom config file

IMPORTANT:
  - This script is ONLY needed for 2-node VCF deployments
  - For 3+ node deployments, this script will exit without making changes
  - Run this script IMMEDIATELY after starting VCF deployment
  - The script will wait for vCenter to be deployed and ready

Requirements:
  - VCF deployment must be in progress
  - vCenter will be deployed by VCF Installer
  - Script will wait up to 30 minutes for each stage
        """
    )

    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Preview changes without executing"
    )

    parser.add_argument(
        "-s", "--skip-wait",
        action="store_true",
        help="Skip waiting for vCenter to be pingable (if already ready)"
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

    # Load configuration
    config = load_config(config_file)

    # Print header
    print(f"{Colors.GREEN}========================================{Colors.NC}")
    print(f"{Colors.GREEN}vSAN ESA Storage Policy Fix Tool{Colors.NC}")
    print(f"{Colors.GREEN}========================================{Colors.NC}\n")

    # Create fixer
    fixer = VSANPolicyFixer(config)

    # Run
    success = fixer.run(dry_run=args.dry_run, skip_wait=args.skip_wait)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
