# VCF Cluster Capacity Overview - Design Document

**Date:** 2024-12-06
**Status:** Approved
**Author:** Claude (with Mark)

## Problem Statement

The existing `vcf_capacity_audit.py` tracks only management VMs defined in the tier configuration. Users need to see total cluster capacity consumption to answer the question: "Can I power on this VM?"

Without visibility into workload VMs and total cluster headroom, users must manually calculate available capacity before starting powered-off VMs.

## Solution Overview

Enhance the capacity audit system to provide cluster-wide capacity visibility while maintaining detailed tracking of managed VMs.

**Two access points:**
- **Quick command**: Fast cluster capacity check for daily use
- **Enhanced audit**: Complete picture with managed VM details plus cluster summary

## Architecture

### Current State

`vcf_capacity_audit.py` connects to vCenter and queries only VMs defined in `config/vcf-management-tiers.yaml`. It calculates detailed statistics and right-sizing recommendations for these managed VMs only.

### Proposed Enhancement

Add `get_cluster_capacity_summary()` method that:

1. Queries all VMs in vCenter (not just tier config VMs)
2. Categorizes VMs into three groups:
   - **Managed VMs**: VMs in tier config (detailed tracking)
   - **Other Running VMs**: Workload VMs currently consuming capacity
   - **Other Powered-Off VMs**: VMs that could be started
3. Calculates total cluster consumption vs. physical capacity
4. Returns available headroom for starting new VMs

### Implementation Approach

**Modify `scripts/vcf_capacity_audit.py`:**

1. **New method**: `get_cluster_capacity_summary()`
   - Query all VMs from vCenter
   - Build set of managed VM names from tier config
   - Categorize each VM: managed vs. other
   - Track power state for other VMs
   - Calculate totals and headroom

2. **New method**: `display_cluster_capacity_summary(summary_data)`
   - Format and print cluster overview
   - Show running vs. powered-off breakdown
   - List powered-off VMs with memory requirements
   - Color-code capacity status

3. **Enhance**: `audit_all_vms()`
   - After managed VM audit, call cluster summary
   - Display cluster capacity at end of report

4. **Add CLI flag**: `--cluster-summary-only`
   - Skip detailed audit
   - Show only cluster capacity overview
   - Fast execution for daily checks

**Add Makefile target:**

```makefile
vcf-cluster-capacity: sync ## Quick cluster capacity overview
    @echo "$(GREEN)Checking cluster capacity...$(NC)"
    @uv run scripts/vcf_capacity_audit.py --cluster-summary-only
```

## Display Format

### Quick Command (`make vcf-cluster-capacity`)

```
================================================================================
VCF Cluster Capacity Overview
Generated: 2024-12-06 14:23:15
================================================================================

Physical Cluster Capacity: 384 GB

Memory Allocation by Category:
────────────────────────────────────────────────────────────────────────────
  Management VMs (Running):      207.0 GB   (53.9%)  [8 VMs]
  Other VMs (Running):            45.2 GB   (11.8%)  [12 VMs]
  Other VMs (Powered Off):        87.0 GB   (22.7%)  [5 VMs]
────────────────────────────────────────────────────────────────────────────
  Total Allocated (Running):     252.2 GB   (65.7%)  [20 VMs]
  Available Headroom:            131.8 GB   (34.3%)

Capacity Status: ✓ HEALTHY - Sufficient headroom available

Powered-Off VMs You Could Start:
  • auto01 (87.0 GB) - Would use 66% of available headroom
  • test-vm-1 (16.0 GB)
  • test-vm-2 (8.0 GB)
```

### Enhanced Audit (`make vcf-capacity-audit`)

Existing detailed audit output remains unchanged. Cluster capacity summary appends to the end.

### Display Features

- **Visual organization**: Clear sections with separators
- **Percentages**: Show allocation as percentage of total capacity
- **VM counts**: Number of VMs in each category
- **Status indicator**:
  - ✓ HEALTHY (<70% used)
  - ⚠ WARNING (70-85% used)
  - 🚨 CRITICAL (>85% used)
- **Actionable info**: List powered-off VMs with impact on headroom

## Resource Tracking

**Memory only** - Primary constraint in homelab environments.

CPU and storage are separate concerns and rarely block VM startup decisions.

## VM Categorization Logic

```python
# Build set of managed VM names from tier config
managed_vm_names = set()
for tier in config["tiers"].values():
    for vm_config in tier["vms"]:
        managed_vm_names.add(vm_config["name"])

# Query all VMs from vCenter
all_vms = get_all_vms_from_vcenter()

# Categorize each VM
for vm in all_vms:
    if vm.name in managed_vm_names:
        category = "managed"
    elif vm.runtime.powerState == "poweredOn":
        category = "other_running"
    else:
        category = "other_powered_off"
```

## Edge Cases

### No Workload VMs

Display: "Other VMs: 0 GB (0 VMs)"
Don't show powered-off section if none exist.

### Over-Provisioned Cluster

Show negative headroom: "⚠ OVERCOMMITTED: -15.2 GB"
Display warning about memory pressure.

### VM in Config Missing from vCenter

Already handled by existing code (marks as "NOT FOUND").
Don't count toward managed VM totals.

### VMs with Memory Balloon/Reservation

Use `config.memorySizeMB` (allocated memory).
Consistent with current audit logic.

## Configuration Requirements

Uses existing configuration in `config/vcf-management-tiers.yaml`:

```yaml
homelab:
  total_physical_ram_gb: 384  # Required for capacity calculations
```

No new configuration needed.

## Performance

- **Quick command**: ~2-3 seconds (single vCenter API call)
- **Full audit**: Unchanged (already queries each managed VM individually)

## Validation

- vCenter connectivity (already handled)
- Tier config exists (already handled)
- `total_physical_ram_gb` set in config (already required)

## Breaking Changes

None. Only additions to existing functionality.

- Existing commands work exactly as before
- New command provides additional capability
- Enhanced audit adds information, doesn't change existing output

## Testing Approach

1. **Unit-level**: VM categorization logic
2. **Integration**: vCenter API calls
3. **Manual**:
   - Run with no workload VMs
   - Run with over-provisioned cluster
   - Verify powered-off VM list accuracy
   - Test both quick command and enhanced audit

## Documentation Updates

- Add to `docs/VCF_MANAGEMENT_CAPACITY.md`
- Add to `docs/VCF_MANAGEMENT_CAPACITY_QUICKREF.md`
- Update README.md Makefile commands section

## Benefits

1. **Quick decision-making**: "Can I start this VM?" answered in seconds
2. **Complete visibility**: See all capacity consumers, not just managed VMs
3. **No manual calculation**: Automatic headroom calculation
4. **Actionable insights**: See what VMs could be started with available capacity
5. **Backward compatible**: Existing workflows unchanged

## Implementation Tasks

1. Add `get_cluster_capacity_summary()` method
2. Add `display_cluster_capacity_summary()` method
3. Enhance `audit_all_vms()` to call cluster summary
4. Add `--cluster-summary-only` CLI flag
5. Add `vcf-cluster-capacity` Makefile target
6. Update documentation
7. Test with various scenarios
8. Commit and push changes
