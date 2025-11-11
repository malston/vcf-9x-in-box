#!/usr/bin/env python3
"""
Check Secrets Status
Purpose: Display current secrets configuration and sources
"""

import sys
from pathlib import Path

from vcf_secrets import SecretsManager

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))


def main():
    """
    Main entry point for the VCF secrets status checker.

    This function initializes the SecretsManager for the project directory and
    displays the current status of all secrets. It provides a formatted output
    showing which secrets are set and their sources (environment variables or
    encrypted files).

    The function prints a status report that includes:
    - A header banner
    - Detailed secrets information from SecretsManager
    - A footer with reference to additional documentation

    Returns:
        None

    Raises:
        Any exceptions raised by SecretsManager initialization or get_secrets_info()

    Note:
        This script is designed to be run from the command line to check the
        status of VCF (VMware Cloud Foundation) secrets in the project.
    """
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent

    secrets_mgr = SecretsManager(project_dir)

    print("\n" + "=" * 60)
    print("VCF Secrets Status")
    print("=" * 60 + "\n")

    print(secrets_mgr.get_secrets_info())

    print("\n" + "=" * 60)
    print("\nFor more information, see: docs/SECRETS_MANAGEMENT.md\n")


if __name__ == "__main__":
    main()
