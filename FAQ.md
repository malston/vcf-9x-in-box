# VCF 9.x in a Box - Frequently Asked Questions (FAQ)

## Table of Contents

- [USB Drive and Installation](#usb-drive-and-installation)
- [ESXi Installation](#esxi-installation)
- [NVMe Device Identifiers](#nvme-device-identifiers)
- [VCF Deployment](#vcf-deployment)
- [Network Configuration](#network-configuration)
- [Troubleshooting](#troubleshooting)

---

## USB Drive and Installation

### Do I need 3 separate USB drives: one for each host?

**No, you don't need 3 separate USB drives!** You can use **one USB drive** and reuse it for each host.

#### Sequential Installation (1 USB drive)

This is the recommended approach:

```bash
# Use the same USB drive for each host
sudo make usb-create USB=/dev/disk4 HOST=1
# Insert in host 1, boot, wait ~20 minutes for install to complete

sudo make usb-create USB=/dev/disk4 HOST=2  # Overwrites USB
# Insert in host 2, boot, wait ~20 minutes

sudo make usb-create USB=/dev/disk4 HOST=3  # Overwrites USB
# Insert in host 3, boot, wait ~20 minutes

Total time: ~60 minutes (sequential)
```

Each `make usb-create` command **overwrites** the USB drive with the new kickstart config for that specific host.

#### Parallel Installation (3 USB drives)

If you **do** have 3 USB drives, you can install all hosts simultaneously:

```bash
# Create 3 different USB drives
sudo make usb-create USB=/dev/disk4 HOST=1
sudo make usb-create USB=/dev/disk5 HOST=2
sudo make usb-create USB=/dev/disk6 HOST=3

# Insert all 3 USB drives into all 3 hosts and power on
# All hosts install in parallel

Total time: ~20 minutes (parallel)
```

#### Recommendation

**Use 1 USB drive** (sequential) unless:

- You're in a hurry and want to save 40 minutes
- You already have multiple USB drives available
- You want to minimize the number of times you need to physically access the hardware

---

### Does it matter if there's a previous installation of ESXi already on the host when we boot from the USB drive?

**No, it doesn't matter!** The kickstart configuration handles this automatically.

#### Why It Doesn't Matter

Your kickstart configs include the `--overwritevmfs` flag:

```bash
# From your ks-esx01.cfg (and all generated configs)
install --disk=t10.NVMe____Samsung_SSD_980_500GB___... --overwritevmfs
```

The `--overwritevmfs` flag tells the ESXi installer to:

- **Overwrite any existing VMFS partitions** on the target disk
- **Destroy all existing data** on the install disk
- **Perform a clean installation** without prompting

#### What This Means

✅ **Works with previous ESXi installations** (any version)
✅ **Works with existing VMFS datastores**
✅ **Works with other OS installations** (Linux, Windows, etc.)
✅ **Works with blank/new disks**
✅ **No manual cleanup needed**

The installation will proceed automatically without any user interaction, regardless of what's currently on the disk.

#### Important Notes

⚠️ **All data on the install disk will be destroyed**

- The install disk specified in your config will be completely wiped
- Any VMs, datastores, or other data on that disk will be lost
- This is intentional and expected for a fresh ESXi deployment

✅ **Other disks are safe**

- Only the disk specified as `install_disk` in `vcf-config.yaml` is affected
- Your `tiering_disk` and other NVMe drives remain untouched during initial install
- The kickstart `%firstboot` section configures those disks later

#### Your Configuration Example

From `config/vcf-config.yaml`:

```yaml
hosts:
  - number: 1
    install_disk: "t10.NVMe____Samsung_SSD_980_500GB___7F17A051D3382500"  # ← Only this disk is wiped
    tiering_disk: "t10.NVMe____Samsung_SSD_990_PRO_4TB___72A9415145382500"  # ← Safe during install
```

**Bottom line:** You can boot from the USB and reinstall ESXi 9.0.0.0 as many times as you want without any manual disk cleanup!

---

## ESXi Installation

### How long does the ESXi installation take?

**Approximately 15-20 minutes per host**, broken down as:

- Initial installation: ~5 minutes
- First reboot: ~2 minutes
- Firstboot configuration: ~5-10 minutes
- Second reboot: ~2 minutes
- Final boot and ready: ~2 minutes

Total hands-off time once you insert the USB and power on.

### How do I know the installation is complete?

**Signs the installation is complete:**

1. **No more reboots happening**
2. **ESXi console shows login screen** with:
   - Hostname (e.g., `esx01.vcf.lab`)
   - IP address (e.g., `172.30.0.10`)
   - ESXi version: `VMware ESXi 9.0.0 build-24755229`

3. **Can access via web browser:**
   - Navigate to `https://172.30.0.10` (or .11, .12)
   - Should see ESXi web interface

4. **SSH is accessible:**

   ```bash
   ssh root@172.30.0.10
   # Should connect without errors
   ```

### What happens if I remove the USB drive during installation?

**During initial install:** Installation will fail. The installer reads from the USB throughout the process.

**After first reboot:** Safe to remove. ESXi has been copied to the NVMe disk and no longer needs the USB.

**Best practice:** Leave the USB inserted until you see the ESXi login screen, then it's safe to remove.

---

## NVMe Device Identifiers

### How do I find my NVMe device identifiers?

**Method 1: Using ESXi Installer Console (Recommended)**

1. Boot ESXi installer from USB (without kickstart, or any ESXi ISO)
2. Press **ALT+F1** at the installer screen
3. Login as `root` (password: blank, just press Enter)
4. Enable SSH: `/etc/init.d/SSH start`
5. Note the IP address shown on screen
6. From another computer: `ssh root@<ip-address>`
7. Run: `vdq -q`
8. Copy the full device identifiers

**Example output:**

```
t10.NVMe____Samsung_SSD_980_500GB___________________7F17A051D3382500
t10.NVMe____Samsung_SSD_990_PRO_4TB_________________72A9415145382500
```

**Method 2: From Running ESXi Host**

If you already have ESXi installed:

```bash
ssh root@172.30.0.10
esxcli storage core device list | grep -i "Display Name\|Device Type"
```

### Why do I need exact device identifiers?

**Because:**

- Each NVMe drive has a unique identifier
- Even identical drive models have different serial numbers
- The kickstart needs exact identifiers to target the correct disk
- Wrong identifier = installation fails or installs to wrong disk

### What if I use the wrong identifier?

**Possible outcomes:**

- Installation fails with "disk not found" error
- Installation succeeds but uses wrong disk (data loss on unexpected disk)
- Host doesn't boot properly after installation

**Prevention:** Always verify identifiers using `vdq -q` on each physical host before generating kickstart configs.

---

## VCF Deployment

### Do I need to run the vSAN policy fix script for 3-node deployments?

**No!** The script automatically detects your host count and skips execution if not needed.

From your `config/vcf-config.yaml`:

```yaml
hosts:
  - number: 1
  - number: 2
  - number: 3  # ← 3 hosts = no fix needed
```

**What happens:**

- Script reads config and counts hosts
- If 3+ hosts: Prints message and exits (no changes made)
- If 2 hosts: Performs the FTT=0 policy fix

**You can safely run** `make fix-vsan-policy` regardless of host count - it's smart enough to know when it's needed.

### When exactly should I run the vSAN policy fix script?

**Timing:** **IMMEDIATELY** after clicking "DEPLOY" in the VCF Installer UI

**Why this timing:**

1. VCF starts deploying vCenter Server
2. vCenter creates default vSAN policy (FTT=1, requires 3 hosts)
3. Script waits for vCenter to be ready
4. Script detects policy creation
5. Script updates policy to FTT=0 (works with 2 hosts)
6. VCF deployment continues successfully

**Too early:** Script will wait (not a problem, just wastes time)
**Too late:** VCF deployment may fail before policy is fixed
**Just right:** Run immediately after starting deployment

### Can I preview what the scripts will do before running them?

**Yes!** All Python scripts support `--dry-run` mode:

```bash
# Preview VCF Installer deployment
make deploy-vcf-installer-dry-run

# Preview VCF Installer configuration
make setup-vcf-installer-dry-run

# Preview vSAN policy fix
make fix-vsan-policy-dry-run

# Or with Python directly
uv run scripts/deploy_vcf_installer.py --dry-run
uv run scripts/setup_vcf_installer.py --dry-run
uv run scripts/fix_vsan_esa_default_storage_policy.py --dry-run
```

**What dry-run shows:**

- Exactly what commands would be executed
- What files would be modified
- What API calls would be made
- Configuration values that would be used
- **No actual changes are made**

### What ESXi version must I use?

**Required:** ESXi 9.0.0.0 build 24755229

**Why this specific build:**

- VCF 9.0.0.0 requires specific ESXi versions
- Version compatibility is strictly enforced
- Mismatch causes deployment failures
- This build is documented in VCF 9.0.0.0 release notes

**How to verify:**

```bash
ssh root@172.30.0.10 "vmware -v"
# Must show: VMware ESXi 9.0.0 build-24755229
```

**Where to find:**

- Broadcom Support Portal: <https://support.broadcom.com/>
- Path in offline depot: `PROD/COMP/ESX_HOST/`
- Filename: `VMware-VMvisor-Installer-9.0.0.0.24755229.x86_64.iso`

---

## Network Configuration

### Can I use different VLANs than the defaults?

**Yes!** Edit `config/vcf-config.yaml`:

```yaml
network:
  vlan_id: "30"  # ← Change to your management VLAN
```

**Requirements:**

- VLAN must exist on your physical switch
- VLAN must be configured as tagged/trunked to the ESXi hosts
- All hosts must use the same management VLAN
- Additional VLANs (vMotion, vSAN, etc.) are configured in the VCF manifest

### Do I need 10GbE networking?

**Recommended but not strictly required:**

**Minimum (will work):**

- 2x 1GbE NICs per host
- May see performance warnings during VCF validation

**Recommended:**

- 2x 10GbE NICs per host (what MS-A2 provides)
- Better performance for vSAN, vMotion, and production workloads

**Note:** Some MikroTik switches may fail MTU validation during VCF deployment. This is a known issue and can be acknowledged/bypassed if you've confirmed Jumbo Frames are configured correctly.

### Can I change IP addresses after installation?

**Before VCF deployment:** Yes, relatively easy

- Regenerate kickstart configs with new IPs
- Reinstall ESXi on hosts (overwrites everything)

**After VCF deployment:** Difficult, not recommended

- VCF has configured vCenter, NSX, distributed switches, etc.
- IP changes require extensive reconfiguration
- May break existing VCF deployment
- Better to redeploy from scratch if IPs must change

**Best practice:** Plan your IP addressing carefully before starting.

---

## Troubleshooting

### The kickstart doesn't seem to be running (interactive installer starts)

**Check these items:**

1. **Verify KS.CFG exists on USB:**

   ```bash
   ls /Volumes/ESXi/KS.CFG
   # Should show the file
   ```

2. **Verify BOOT.CFG was modified:**

   ```bash
   cat /Volumes/ESXi/EFI/BOOT/BOOT.CFG | grep kernelopt
   # Should show: kernelopt=ks=usb:/KS.CFG
   ```

3. **Check USB was created correctly:**

   ```bash
   # Recreate USB with verbose output
   sudo uv run scripts/create_esxi_usb.py /dev/disk4 1
   # Watch for any error messages
   ```

4. **Try dry-run first:**

   ```bash
   uv run scripts/create_esxi_usb.py --dry-run /dev/disk4 1
   # Verify all steps look correct
   ```

### ESXi installed but I can't SSH to it

**Common causes:**

1. **Wrong IP address or host not fully booted:**

   ```bash
   # Ping first
   ping 172.30.0.10

   # Check from ESXi console - should show IP
   # Wait for both reboots to complete (~20 min total)
   ```

2. **Firewall blocking SSH:**

   ```bash
   # From ESXi console, press ALT+F1
   # Check if SSH is running:
   /etc/init.d/SSH status
   ```

3. **DNS not resolving:**

   ```bash
   # Use IP instead of hostname
   ssh root@172.30.0.10  # Instead of root@esx01.vcf.lab
   ```

4. **Kickstart firstboot didn't complete:**

   ```bash
   # Check if host has rebooted twice
   # First reboot: basic install
   # Second reboot: firstboot configuration (enables SSH)
   ```

### VCF Installer deployment fails with "datastore not found"

**Cause:** Datastore name mismatch

**Solution:**

1. **Check actual datastore name on ESXi:**

   ```bash
   ssh root@172.30.0.10 "esxcli storage filesystem list"
   # Note the exact datastore name
   ```

2. **Verify it matches config:**

   ```yaml
   # config/vcf-config.yaml
   hosts:
     - number: 1
       datastore_name: "local-vmfs-datastore-1"  # ← Must match exactly
   ```

3. **If mismatch, update config and redeploy:**

   ```bash
   vim config/vcf-config.yaml  # Fix datastore name
   make deploy-vcf-installer
   ```

### Can I stop and restart a VCF deployment?

**Short answer:** Not easily. VCF deployments should run to completion.

**If deployment fails:**

- Review logs in VCF Installer UI for specific error
- Fix the underlying issue (DNS, networking, etc.)
- **Usually need to redeploy from scratch:**
  - Reinstall ESXi on all hosts (clears previous partial deployment)
  - Redeploy VCF Installer VM
  - Start VCF deployment again

**Prevention:**

- Validate all prerequisites before starting
- Use dry-run mode to preview configurations
- Ensure DNS entries are correct
- Verify network/VLAN configuration
- Check all IPs are reachable

---

## General Questions

### How long does the complete deployment take?

**Total time: 5-6 hours**, broken down as:

| Phase | Duration | Notes |
|-------|----------|-------|
| Edit config YAML | 15 min | One-time setup |
| Generate kickstart | <1 min | Automated |
| Create USB (per host) | 5-10 min | Can parallel with 3 USBs |
| Install ESXi (per host) | 15-20 min | Can parallel with 3 USBs |
| Deploy VCF Installer | 10 min | Automated |
| Configure VCF Installer | 5 min | Automated |
| Download binaries | 30-60 min | Depends on network speed |
| VCF deployment | 3-4 hours | Fully automated |

**Can be parallelized:**

- ESXi installation: 60 min → 20 min (with 3 USB drives)
- Most waiting is during VCF deployment (automated, no intervention)

### Can I use this on hardware other than MS-A2?

**Yes!** The scripts work with any x86-64 hardware that supports ESXi 9.0.

**Requirements:**

- Meets ESXi 9.0 hardware requirements
- Has NVMe or SAS/SATA storage
- Has at least 2 NICs (1GbE or 10GbE)
- Meets VCF minimum specs (16C/32T, 128GB RAM recommended)

**Configuration changes needed:**

- Update NVMe device identifiers in `vcf-config.yaml`
- May need to adjust network device names
- Verify NIC compatibility with ESXi 9.0

### Do I need a license for VCF?

**Yes**, but:

**For evaluation/lab:**

- VCF 9.0 includes 60-day evaluation licenses
- All features enabled during evaluation
- No license keys needed initially

**For production:**

- Requires VCF licenses from Broadcom
- Licenses applied via VCF Operations UI
- Contact Broadcom sales/support for licensing

**This project is designed for:**

- Home lab environments
- Learning and development
- Testing and evaluation
- Not for production use without proper licensing

---

## Additional Resources

- **Main README:** [README.md](README.md)
- **Deployment Workflow:** [DEPLOYMENT_WORKFLOW.md](DEPLOYMENT_WORKFLOW.md)
- **Python Setup:** [PYTHON_SETUP.md](PYTHON_SETUP.md)
- **Standardization Guide:** [PYTHON_STANDARDIZATION.md](PYTHON_STANDARDIZATION.md)

---

**Last Updated:** October 17, 2024

**Have more questions?** Open an issue at: <https://github.com/anthropics/claude-code/issues>
