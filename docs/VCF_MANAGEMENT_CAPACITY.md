# VCF Management VM Capacity Optimization

> **Reclaim 20-30% of your homelab capacity** by intelligently managing VCF 9.x management VMs

## Overview

VCF 9.x deploys numerous management VMs for operations, automation, monitoring, and logging. In a production environment with hundreds of hosts, these VMs are essential. **In a 3-host homelab, many of these components are unused overhead.**

This guide shows you how to:
1. **Audit** actual resource usage vs. allocation
2. **Right-size** management VMs to appropriate homelab configurations
3. **Power down** unused management components to reclaim capacity
4. **Safely power up** components when you need management features

---

## The Problem: Management Overhead

### Typical VCF 9.x Management VM Allocation

| Component | Typical RAM | Typical vCPU | Required? |
|-----------|------------|--------------|-----------|
| vCenter Server | 24 GB | 4 | ✅ Yes - Core infrastructure |
| NSX Manager | 24 GB | 6 | ✅ Yes - Networking |
| NSX Edges (2x) | 16 GB (8x2) | 8 (4x2) | ✅ Yes - Workload routing |
| SDDC Manager | 24 GB | 4 | ✅ Yes - Backend orchestration |
| VCF Operations Console | 16 GB | 4 | ⚠️ Only when managing VCF |
| VCF Operations (vROps) | 32 GB | 8 | ⚠️ Only if using monitoring |
| VCF Automation (vRA) | 32 GB | 8 | ❌ Not needed unless using IaC |
| Identity Broker | 8 GB | 2 | ❌ Not needed for local auth |
| Operations Proxy | 8 GB | 2 | ❌ Not needed air-gapped |
| Operations for Logs | 16 GB | 4 | ❌ Not needed with SSH access |
| Operations for Networks | 8 GB | 2 | ❌ Not needed with NSX Manager UI |
| **TOTAL** | **~208 GB** | **~52 vCPU** | |

**In a 3-host cluster with 384GB total RAM, management consumes 54% of capacity!**

---

## The Solution: Three-Tier Management Strategy

### Tier 1: Critical Infrastructure (Always On)
VMs required for workloads to function:
- vCenter Server
- NSX Manager + Edges
- SDDC Manager (backend services)

### Tier 2: Management-Only Components (Power Down When Not Managing)
VMs used for Day-N lifecycle operations:
- VCF Operations Console (new primary UI for VCF 9.x)
- VCF Operations (vROps) - if you want monitoring

### Tier 3: Optional Features (Power Down If Not Using)
VMs providing features you may not be using:
- VCF Automation (vRA/vRO) - Not needed unless using IaC or self-service
- Identity Broker - Not needed for local admin accounts
- Operations Proxy - Not needed air-gapped
- Operations for Logs - Not needed with SSH/vCenter log access
- Operations for Networks - Not needed with NSX Manager UI

---

## Quick Start

### Step 1: Check Current Status

```bash
# Set vCenter password (required for all operations)
export VCF_VCENTER_PASSWORD='VMware1!VMware1!'

# Show power state of all management VMs
make vcf-status
```

### Step 2: Audit Capacity Usage

```bash
# Run full capacity audit
make vcf-capacity-audit

# Audit specific VM
make vcf-capacity-audit VM=opsfm01

# Export results to CSV for analysis
make vcf-capacity-audit CSV=audit-results.csv
```

**The audit will show:**
- Current resource allocation vs. actual usage
- Right-sizing recommendations for over-allocated VMs
- Total reclaimable capacity by powering down unused VMs

### Step 3: Power Down Unused Components

```bash
# Preview what would happen (dry run)
make vcf-power-down-dryrun TIER=tier3

# Power down all unused Tier 3 VMs
make vcf-power-down TIER=tier3

# Or use the quick command
make vcf-power-down-unused
```

**Expected capacity reclaim: ~72GB RAM (18-20% of 384GB cluster)**

### Step 4: Validate Everything Still Works

```bash
# Check that Tier 1 (critical) VMs are still running
make vcf-validate

# Verify workloads are unaffected
# - Access vCenter UI: https://vc01.vcf.lab
# - Deploy test VM
# - Check NSX overlay networking
```

---

## Detailed Usage

### Power Management Commands

#### Check Status
```bash
# Show all management VMs
make vcf-status

# Show specific tier
make vcf-status TIER=tier3
```

#### Power Down VMs
```bash
# Power down Tier 3 (unused features)
make vcf-power-down TIER=tier3

# Power down Tier 2 (management-only components)
make vcf-power-down TIER=tier2

# Power down ALL management VMs (Tier 2 + Tier 3)
make vcf-power-down TIER=all

# Dry run (preview without making changes)
make vcf-power-down-dryrun TIER=tier3
```

#### Power Up VMs
```bash
# Power up Tier 3 VMs
make vcf-power-up TIER=tier3

# Power up ALL management VMs
make vcf-power-up TIER=all
# Or use the quick command:
make vcf-power-up-all

# Dry run
make vcf-power-up-dryrun TIER=tier3
```

#### Validation
```bash
# Validate environment before power operations
make vcf-validate

# Checks:
# - vCenter connectivity
# - Tier 1 VMs are running
# - (Manual) No active VCF lifecycle operations
```

### Capacity Audit Commands

#### Full Audit
```bash
# Run comprehensive capacity audit
make vcf-capacity-audit

# Shows:
# - All management VMs with resource allocation and usage
# - Right-sizing recommendations
# - Total potential savings from downsizing
# - Total reclaimable capacity from power-down
```

#### VM-Specific Audit
```bash
# Audit specific VM with detailed analysis
make vcf-capacity-audit VM=opsfm01

# Shows:
# - Current allocation vs. actual usage
# - Memory usage percentage with visual bar
# - Storage committed and uncommitted
# - Right-sizing recommendation with confidence level
```

#### Export to CSV
```bash
# Export audit results for analysis
make vcf-capacity-audit CSV=vcf-audit-$(date +%Y%m%d).csv

# CSV includes:
# - All VM statistics
# - Recommendations
# - Potential savings
```

---

## Advanced Configuration

### Customizing VM Tiers

Edit `config/vcf-management-tiers.yaml` to customize which VMs belong to which tier:

```yaml
tiers:
  tier3:
    name: "Optional Features"
    power_management: true
    vms:
      - name: "auto01"
        display_name: "VCF Automation"
        hostname: "auto01.vcf.lab"
        estimated_ram_gb: 32
        estimated_vcpu: 8
        notes: "Not needed unless using IaC"
```

**Fields:**
- `name` - VM name in vCenter
- `display_name` - Human-readable name
- `hostname` - FQDN
- `estimated_ram_gb` / `estimated_vcpu` - Expected allocation
- `optional: true` - VM may not exist in all deployments
- `notes` - Usage notes

### Right-Sizing Recommendations

The audit script provides homelab-specific right-sizing recommendations in the config:

```yaml
homelab:
  right_sizing:
    - vm: "opsfm01"
      current_typical_allocation_gb: 32
      recommended_homelab_gb: 16
      notes: "VMware defaults assume 100+ hosts, 3-host homelab can run on half"
```

**To apply right-sizing:**
1. Power down VM: `make vcf-power-down TIER=tier2`
2. Edit VM in vCenter (reduce RAM allocation)
3. Power up VM: `make vcf-power-up TIER=tier2`

---

## Understanding VCF 9.x Architecture Changes

### The SDDC Manager UI Deprecation

VCF 9.x introduces a significant architectural shift:

**Old World (VCF 4.x - 5.x):**
- SDDC Manager UI = Primary management interface
- vRealize/Aria Operations = Optional add-on

**New World (VCF 9.x):**
- **VCF Operations Console = New primary management interface**
- SDDC Manager UI = Deprecated (warning banner)
- SDDC Manager backend services = Still required

### What You Can (and Can't) Power Down

| Component | Can Power Down? | Notes |
|-----------|----------------|--------|
| SDDC Manager VM | ❌ **NO** | Backend orchestration services required by NSX/vSAN |
| SDDC Manager UI | ✅ Yes | Deprecated anyway, but services must run |
| VCF Operations Console | ⚠️ **Only when not managing** | New primary UI for lifecycle ops |
| VCF Operations (vROps) | ✅ Yes | Monitoring feature, not required for workloads |

**CRITICAL:** The SDDC Manager **VM** must stay powered on even though the UI is deprecated. It provides backend services that NSX and vSAN depend on.

---

## Safety and Best Practices

### Before Powering Down Management VMs

✅ **DO:**
- Run `make vcf-validate` to check environment health
- Verify no active VCF updates/patches in progress
- Ensure no host maintenance operations running
- Check no workload deployments in progress
- Power down Tier 3 first, then Tier 2 if needed

❌ **DON'T:**
- Power down Tier 1 (critical infrastructure) VMs
- Power down during active VCF lifecycle operations
- Power down during workload deployments
- Power down if unsure about VM's purpose

### Powering Up Management VMs

When you need to perform VCF management tasks:

```bash
# Power up all management VMs
make vcf-power-up-all

# Wait for all services to start (5-10 minutes)
# Then access VCF Operations Console: https://vcf01.vcf.lab
```

**Startup order is automatic:**
- Tier 2 VMs power up first (management infrastructure)
- Tier 3 VMs power up second (optional features)
- Each VM waits for VMware Tools before proceeding

---

## Troubleshooting

### "vCenter connection failed"

**Problem:** Cannot connect to vCenter to manage VMs

**Solutions:**
1. Check vCenter password is set:
   ```bash
   echo $VCF_VCENTER_PASSWORD
   # Should show: VMware1!VMware1!
   ```

2. Verify vCenter is running:
   ```bash
   ping vc01.vcf.lab
   ssh root@esx01.vcf.lab "vim-cmd vmsvc/getallvms"
   ```

3. Check vCenter SSH is enabled (may be disabled in VCF)

### "VM not found"

**Problem:** Script cannot find VM by name

**Possible causes:**
1. VM is optional and not deployed in your VCF version
   - Check `optional: true` in config
   - This is normal, script will skip it

2. VM name doesn't match vCenter inventory
   - Check actual VM names: `make list-vms`
   - Update `config/vcf-management-tiers.yaml` if needed

### "Power down timeout"

**Problem:** VM graceful shutdown timeout, forced power off

**This is normal** if:
- VMware Tools not installed/running
- VM is hung or unresponsive
- Shutdown script takes longer than 2 minutes

**The script automatically:**
1. Attempts graceful shutdown (wait 2 minutes)
2. Falls back to forced power off if timeout
3. No data loss risk for stateless management VMs

### "Cannot power down Tier 1"

**Problem:** Script refuses to power down critical infrastructure

**This is intentional protection:**
- Tier 1 VMs (vCenter, NSX, SDDC Manager) are required for workloads
- Powering them down will break your environment
- You must explicitly confirm with "yes" if you really want to do this

**If you need to power down Tier 1:**
1. Understand this will break workloads
2. Have physical ESXi console access
3. Use forced override: `make vcf-power-down TIER=tier1`
4. Type "yes" when prompted

---

## Expected Capacity Reclaim

### 3-Host Cluster (384GB Total RAM)

| Scenario | RAM Reclaim | % of Cluster |
|----------|-------------|--------------|
| Power down Tier 3 only | ~72 GB | 18.75% |
| Power down Tier 2 + Tier 3 | ~120 GB | 31.25% |
| Right-size Tier 2 (keep running) | ~20 GB | 5.2% |
| **Combined approach** | **~140 GB** | **~36%** |

**Combined approach = Most capacity with least disruption:**
1. Power down unused Tier 3 VMs (~72GB)
2. Right-size VCF Operations (vROps) from 32GB → 16GB (~16GB)
3. Right-size VCF Operations Console from 16GB → 12GB (~4GB)
4. Keep critical infrastructure and used features running

This gives you **140GB additional capacity** for workload VMs while maintaining full functionality for features you actually use.

---

## Integration with VCF Deployment Workflow

### During Initial Deployment

VCF Installer deploys all management VMs by default. After deployment completes:

```bash
# 1. Verify deployment successful
make vcf-validate

# 2. Run capacity audit to see actual usage
make vcf-capacity-audit

# 3. Power down unused components
make vcf-power-down-unused

# 4. Verify workloads still function
# Test: Deploy VM, check networking, access vCenter
```

### Before VCF Updates/Patches

Before applying VCF updates, power up all management VMs:

```bash
# 1. Power up everything
make vcf-power-up-all

# 2. Wait for services to start (5-10 minutes)

# 3. Access VCF Operations Console
open https://vcf01.vcf.lab

# 4. Apply updates through Operations Console

# 5. After updates complete, power down again
make vcf-power-down-unused
```

### Periodic Maintenance

Monthly maintenance checklist:

```bash
# 1. Power up management VMs
make vcf-power-up-all

# 2. Check for VCF updates
# Access: https://vcf01.vcf.lab

# 3. Review monitoring dashboards (if using vROps)
# Access: https://opsfm01.vcf.lab

# 4. Run capacity audit to check for growth
make vcf-capacity-audit CSV=audit-$(date +%Y%m).csv

# 5. Power down unused components
make vcf-power-down-unused
```

---

## Script Details

### vcf_management_power.py

**Purpose:** Power management for VCF management VMs

**Features:**
- Graceful shutdown with fallback to forced power off
- Pre-flight validation before operations
- Dry-run mode for safety
- Tier-based power management
- Automatic startup ordering

**Usage:**
```bash
vcf_management_power.py status              # Show current state
vcf_management_power.py power-down tier3    # Power down Tier 3
vcf_management_power.py power-up all        # Power up all management
vcf_management_power.py validate            # Pre-flight checks
vcf_management_power.py --dry-run <command> # Preview mode
```

### vcf_capacity_audit.py

**Purpose:** Detailed capacity usage analysis and right-sizing recommendations

**Features:**
- Real-time resource usage statistics
- Right-sizing recommendations with confidence levels
- Memory usage visualization
- CSV export for trend analysis
- Per-VM detailed analysis

**Usage:**
```bash
vcf_capacity_audit.py                           # Full audit
vcf_capacity_audit.py --vm-name opsfm01         # Audit specific VM
vcf_capacity_audit.py --export-csv audit.csv    # Export results
```

---

## Configuration Files

### config/vcf-management-tiers.yaml

**Purpose:** Define VM tiers and characteristics

**Structure:**
```yaml
vcenter:
  hostname: "vc01.vcf.lab"
  username: "administrator@vsphere.local"

tiers:
  tier1:  # Critical infrastructure
    name: "Critical Infrastructure"
    power_management: false
    vms: [...]

  tier2:  # Management-only
    name: "Management-Only Components"
    power_management: true
    startup_order: 1
    vms: [...]

  tier3:  # Optional features
    name: "Optional Features"
    power_management: true
    startup_order: 2
    vms: [...]

homelab:
  total_physical_ram_gb: 384
  right_sizing: [...]
```

---

## FAQ

### Q: Will powering down management VMs affect my workload VMs?

**A:** No. Tier 2 and Tier 3 VMs provide **management** and **monitoring** features, not runtime services for workloads. Your workload VMs will continue running normally.

### Q: Can I still deploy VMs with vCenter if VCF Operations Console is powered down?

**A:** Yes. vCenter Server (Tier 1, always on) handles all VM operations. VCF Operations Console is only needed for VCF-specific lifecycle management (patching, host additions, etc.).

### Q: What happens if I need to patch VCF while management VMs are powered down?

**A:** Power them back up first:
```bash
make vcf-power-up-all
```
Wait 5-10 minutes for services to start, then proceed with patching through VCF Operations Console.

### Q: Is it safe to power down SDDC Manager?

**A:** **NO.** The SDDC Manager VM must stay powered on. While the UI is deprecated, the backend services are required by NSX and vSAN. The config file prevents this by default.

### Q: How do I know which VMs I'm actually using?

**A:** Run the capacity audit:
```bash
make vcf-capacity-audit
```

If you see VMs with very low usage (<10%), and you don't recognize the features they provide, they're probably safe to power down.

### Q: Can I right-size management VMs instead of powering them down?

**A:** Yes! That's actually the recommended approach for VMs you want to keep running (like vROps if you're using monitoring). The audit script provides homelab-specific recommendations.

### Q: What if I power something down by mistake?

**A:** Just power it back up:
```bash
make vcf-power-up TIER=tier3
# Or for everything:
make vcf-power-up-all
```

Management VMs are stateless - they retain their configuration across power cycles.

---

## Support and Contributions

This capacity management feature is part of the VCF 9.x in a Box project.

**Issues or Questions:**
- GitHub Issues: [vcf-9x-in-box](https://github.com/example/vcf-9x-in-box/issues)
- Check existing documentation in `/docs/`

**Contributing:**
- Submit pull requests for improvements
- Share your capacity savings in Issues
- Report bugs or unexpected behavior

---

## Changelog

### Version 1.0 (2024-12-04)
- Initial release
- Three-tier management strategy
- Power management scripts with dry-run support
- Capacity audit with right-sizing recommendations
- Makefile integration
- Comprehensive documentation

---

## License

Same as parent project: MIT License
