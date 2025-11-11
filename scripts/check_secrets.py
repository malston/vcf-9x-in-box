#!/usr/bin/env python3
"""
Check Secrets Status
Purpose: Display current secrets configuration and sources
"""

import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from vcf_secrets import SecretsManager


def main():
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent

    secrets_mgr = SecretsManager(project_dir)

    print("\n" + "=" * 60)
    print("VCF Secrets Status")
    print("=" * 60 + "\n")

    print(secrets_mgr.get_secrets_info())

    print("\n" + "=" * 60)
    print("\nFor more information, see: SECRETS_MANAGEMENT.md\n")


if __name__ == "__main__":
    main()
