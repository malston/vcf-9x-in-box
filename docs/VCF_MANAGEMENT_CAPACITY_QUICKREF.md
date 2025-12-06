# VCF Management Capacity - Quick Reference

> **TL;DR:** Reclaim ~20% of homelab capacity by powering down unused VCF management VMs

## One-Time Setup

```bash
# Set vCenter password (add to your ~/.bashrc or ~/.zshrc)
export VCF_VCENTER_PASSWORD='VMware1!VMware1!'
```

## Most Common Commands

```bash
# Check what's running
make vcf-status

# See how much capacity you can reclaim
make vcf-capacity-audit

# Power down unused management VMs (~72GB reclaimed)
make vcf-power-down-unused

# Power everything back up (when you need to manage VCF)
make vcf-power-up-all
```

## The Three Tiers

### Tier 1: Always On (Don't Touch)
- vCenter, NSX, SDDC Manager
- Required for workloads to function

### Tier 2: Management-Only (Power Down When Not Managing)
- VCF Operations Console (new primary UI)
- VCF Operations (vROps monitoring)

### Tier 3: Optional Features (Safe to Power Down)
- VCF Automation (vRA) - if not using IaC
- Identity Broker - if using local admin only
- Operations Proxy, Logs, Networks - if not using features

## Step-by-Step: First Time

```bash
# 1. Check current state
make vcf-status

# 2. See capacity analysis
make vcf-capacity-audit

# 3. Preview what would happen
make vcf-power-down-dryrun TIER=tier3

# 4. Power down unused VMs
make vcf-power-down-unused

# 5. Verify workloads still work
# - Access vCenter: https://vc01.vcf.lab
# - Deploy test VM
# - Check networking
```

## All Power Management Commands

| Command | Description |
|---------|-------------|
| `make vcf-status` | Show power state of all management VMs |
| `make vcf-status TIER=tier3` | Show specific tier |
| `make vcf-validate` | Run pre-flight checks |
| `make vcf-capacity-audit` | Full capacity analysis |
| `make vcf-capacity-audit VM=opsfm01` | Audit specific VM |
| `make vcf-power-down-unused` | Power down Tier 3 (quick command) |
| `make vcf-power-down TIER=tier3` | Power down Tier 3 |
| `make vcf-power-down TIER=tier2` | Power down Tier 2 |
| `make vcf-power-down TIER=all` | Power down all management |
| `make vcf-power-up TIER=tier3` | Power up Tier 3 |
| `make vcf-power-up-all` | Power up everything (quick command) |
| `make vcf-power-down-dryrun TIER=tier3` | Preview power down |

## Expected Capacity Reclaim

| Action | RAM Reclaimed | % of 384GB Cluster |
|--------|---------------|-------------------|
| Power down Tier 3 | ~72 GB | ~19% |
| Power down Tier 2+3 | ~120 GB | ~31% |
| Right-size + Power down | ~140 GB | ~36% |

## When to Power Up Management VMs

Before any of these activities:
- Applying VCF patches/updates
- Adding/removing hosts
- Changing VCF configuration
- Using VCF Operations Console UI

```bash
make vcf-power-up-all
# Wait 5-10 minutes for services to start
# Then access: https://vcf01.vcf.lab
```

## Troubleshooting

### "vCenter connection failed"
```bash
# Check password is set
echo $VCF_VCENTER_PASSWORD

# If not set:
export VCF_VCENTER_PASSWORD='VMware1!VMware1!'
```

### "VM not found"
- Probably an optional VM that wasn't deployed
- Check with: `make list-vms`
- This is normal for optional VMs

### "Cannot power down Tier 1"
- This is intentional protection
- Tier 1 VMs are required for workloads
- Don't power them down unless you know what you're doing

## Integration with Workflows

### After VCF Deployment
```bash
make vcf-validate              # Verify deployment
make vcf-capacity-audit        # See current usage
make vcf-power-down-unused     # Reclaim capacity
```

### Monthly Maintenance
```bash
make vcf-power-up-all          # Power up management
# Check for updates via https://vcf01.vcf.lab
# Apply updates if needed
make vcf-capacity-audit        # Check usage trends
make vcf-power-down-unused     # Power down again
```

### Before Workload Deployments
```bash
# Check if you have capacity
make vcf-capacity-audit

# If needed, check what's powered on
make vcf-status

# Verify Tier 1 is running (should always be)
make vcf-validate
```

## Advanced Usage

### Export Audit Results
```bash
make vcf-capacity-audit CSV=vcf-audit-$(date +%Y%m%d).csv
```

### Audit Specific VM
```bash
make vcf-capacity-audit VM=opsfm01
```

### Right-Sizing VMs

After identifying over-allocated VMs in audit:

1. Power down the VM:
   ```bash
   make vcf-power-down TIER=tier2
   ```

2. Edit VM in vCenter (reduce RAM allocation)

3. Power back up:
   ```bash
   make vcf-power-up TIER=tier2
   ```

## Safety Notes

✅ **Safe to do:**
- Power down Tier 3 anytime
- Power down Tier 2 when not managing VCF
- Run dry-run commands
- Check status frequently

❌ **Don't do:**
- Power down Tier 1 (critical infrastructure)
- Power down during VCF updates/patches
- Power down during workload deployments

## Environment Variables

```bash
# Required for all commands
export VCF_VCENTER_PASSWORD='your-vcenter-password'

# Optional: use different config file
export CONFIG='path/to/vcf-config.yaml'
```

## Configuration Files

| File | Purpose |
|------|---------|
| `config/vcf-management-tiers.yaml` | VM tier definitions |
| `config/vcf-config.yaml` | vCenter connection settings |

## Getting Help

```bash
# See all available commands
make help

# Command-specific help
vcf_management_power.py --help
vcf_capacity_audit.py --help
```

## Full Documentation

For detailed explanations, troubleshooting, and architecture details:
- [`docs/VCF_MANAGEMENT_CAPACITY.md`](./VCF_MANAGEMENT_CAPACITY.md)
