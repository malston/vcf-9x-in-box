# VCF 9.x Deployment Workflow Guide

This guide explains the complete deployment workflow from generating kickstart configs to deploying VCF, showing how each step connects to the next.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Complete Workflow](#complete-workflow)
- [Step-by-Step Process](#step-by-step-process)
- [File Dependencies](#file-dependencies)
- [Troubleshooting](#troubleshooting)

---

## Overview

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Configure                                               │
│ Edit config/vcf-config.yaml                                     │
│ └─> Defines: IPs, hostnames, NVMe disks, network settings      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Generate Kickstart Configs                             │
│ Run: make generate                                              │
│ └─> Creates: ks-esx01.cfg, ks-esx02.cfg, ks-esx03.cfg          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Create Bootable USB Installers                         │
│ Run: sudo make usb-create USB=/dev/disk2 HOST=1 (repeat x3)    │
│ └─> Creates: ESXi 9.0.0.0 USB installer with kickstart config  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Install ESXi on Physical Hosts                         │
│ Boot each MS-A2 from USB                                        │
│ └─> Result: 3 ESXi 9.0.0.0 hosts at 172.30.0.10, .11, .12      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Deploy VCF Installer Appliance                         │
│ Run: ./scripts/deploy_vcf_installer.sh                          │
│ └─> Result: VCF Installer VM at 172.30.0.21                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 6: Configure VCF Installer                                │
│ Run: ./scripts/setup_vcf_installer.ps1                          │
│ └─> Result: VCF Installer ready to deploy VCF                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 7: Deploy VCF Management Domain                           │
│ Upload manifest, start deployment                               │
│ └─> Result: Complete VCF 9.0 environment                       │
└─────────────────────────────────────────────────────────────────┘
```

### Why This Order Matters

Each step **depends on the previous step** being completed successfully:

1. **Config → Kickstart:** Can't generate kickstart configs without knowing host IPs and disk layouts
2. **Kickstart → USB:** Can't create USB installers without kickstart configs to embed
3. **USB → ESXi Install:** Can't install ESXi without bootable USB with kickstart
4. **ESXi → VCF Installer:** VCF Installer VM must run on ESXi (chicken/egg: need ESXi first)
5. **VCF Installer → VCF Deployment:** VCF Installer orchestrates the entire VCF deployment

---

## Prerequisites

### Required Software

- **ESXi 9.0.0.0 ISO** (build 24755229) - MUST match VCF 9.0.0.0 version
- **VCF Installer OVA** (SDDC Manager appliance)
- **VCF Offline Depot** with all binaries
- **Python 3.8+** with `uv` package manager
- **OVFTool** for deploying VCF Installer
- **PowerShell 7+** with PowerCLI module

### Required Hardware

- **3x Physical Hosts** (e.g., Minisforum MS-A2)
  - 16C/32T CPU minimum
  - 128GB RAM minimum
  - Multiple NVMe drives
  - 2x 10GbE NICs
- **USB Drive** (16GB+ for ESXi installer)
- **10GbE Switch** with VLAN support

---

## Complete Workflow

### Step 1: Configure Deployment Settings

**File:** `config/vcf-config.yaml`

**What It Defines:**

```yaml
# Network settings used by ALL hosts
network:
  gateway: "172.30.0.1"
  vlan_id: "30"
  dns_server: "192.168.10.2"

# Common settings for ALL hosts
common:
  root_password: "VMware1!"
  ntp_server: "pool.ntp.org"
  esxi_iso_path: "/path/to/VMware-VMvisor-Installer-9.0.0.0.24755229.x86_64.iso"

# Per-host settings
hosts:
  - number: 1
    hostname: "esx01.vcf.lab"
    ip: "172.30.0.10"
    install_disk: "t10.NVMe____Samsung_SSD_980_500GB___..."
    tiering_disk: "t10.NVMe____Samsung_SSD_990_PRO_4TB___..."
```

**Action Required:**

1. Edit `config/vcf-config.yaml`
2. Update IPs, hostnames, passwords
3. **CRITICAL:** Update NVMe device identifiers (see [Finding NVMe Identifiers](#finding-nvme-identifiers))

**Output:** Configuration ready for kickstart generation

---

### Step 2: Generate ESXi Kickstart Configs

**Script:** `scripts/generate_kickstart.py`

**What It Does:**

1. Reads `config/vcf-config.yaml`
2. Loads Jinja2 template `config/ks-template.cfg.j2`
3. Generates one kickstart config per host
4. Writes configs to `config/` directory

**How It Works:**

```python
# Template has variables like {{ host_ip }}, {{ hostname }}, etc.
# Script replaces them with values from YAML for each host

Template: config/ks-template.cfg.j2
   ↓ (render with host 1 data)
Output: config/ks-esx01.cfg

Template: config/ks-template.cfg.j2
   ↓ (render with host 2 data)
Output: config/ks-esx02.cfg

Template: config/ks-template.cfg.j2
   ↓ (render with host 3 data)
Output: config/ks-esx03.cfg
```

**Commands:**

```bash
# Generate all kickstart configs
make generate

# Or generate for specific host
make generate-1  # Just esx01
make generate-2  # Just esx02
make generate-3  # Just esx03

# Or use Python directly
uv run scripts/generate_kickstart.py all
```

**Input Files:**

- `config/vcf-config.yaml` (configuration)
- `config/ks-template.cfg.j2` (Jinja2 template)

**Output Files:**

- `config/ks-esx01.cfg` (ESXi kickstart for host 1)
- `config/ks-esx02.cfg` (ESXi kickstart for host 2)
- `config/ks-esx03.cfg` (ESXi kickstart for host 3)

**What's In The Kickstart Files:**

```bash
# ESXi installation settings
install --disk=<NVMe device> --overwritevmfs
rootpw VMware1!

# Network configuration
network --bootproto=static --ip=172.30.0.10 --netmask=255.255.255.0 \
        --gateway=172.30.0.1 --hostname=esx01.vcf.lab --vlanid=30

# Post-installation commands (firstboot)
%firstboot --interpreter=busybox
- Configure NTP
- Configure DNS
- Create vSwitch with MTU 9000
- Configure NVMe tiering
- Create local VMFS datastore
- Enable SSH/ESXi Shell
- Reboot
```

**Dry Run (Preview):**

```bash
# See what would be generated without writing files
uv run scripts/generate_kickstart.py --help
```

---

### Step 3: Create Bootable ESXi USB Installers

**Script:** `scripts/create_esxi_usb.py`

**What It Does:**

1. Takes ESXi 9.0.0.0 ISO
2. Writes ISO to USB drive
3. Copies kickstart config to USB as `KS.CFG`
4. Modifies `BOOT.CFG` to use kickstart (automated installation)

**How It Works:**

```
Input:
  - ESXi ISO: VMware-VMvisor-Installer-9.0.0.0.24755229.x86_64.iso
  - Kickstart: config/ks-esx01.cfg
  - USB Device: /dev/disk2

Process:
  1. Unmount USB device
  2. Write ISO to USB using dd (creates bootable USB)
  3. Mount USB partition
  4. Copy ks-esx01.cfg → /Volumes/ESXi/KS.CFG
  5. Edit /Volumes/ESXi/EFI/BOOT/BOOT.CFG
     Before: kernelopt=<interactive installer options>
     After:  kernelopt=ks=usb:/KS.CFG
  6. Unmount and eject USB

Output:
  - Bootable ESXi USB installer with embedded kickstart config
```

**Commands:**

```bash
# Dry run first (no root required, preview only)
uv run scripts/create_esxi_usb.py --dry-run /dev/disk2 1

# List available USB devices
make usb-list

# Create USB for host 1
sudo make usb-create USB=/dev/disk2 HOST=1

# Create USB for host 2 (use same USB, recreates it)
sudo make usb-create USB=/dev/disk2 HOST=2

# Create USB for host 3
sudo make usb-create USB=/dev/disk2 HOST=3

# Or use Python directly
sudo uv run scripts/create_esxi_usb.py /dev/disk2 1
```

**Input Files:**

- ESXi ISO (from `esxi_iso_path` in config or `-i` flag)
- Kickstart config: `config/ks-esx0X.cfg`
- USB device: `/dev/diskX`

**Output:**

- Bootable USB drive ready to install ESXi on specific host

**What The USB Contains After Creation:**

```
/Volumes/ESXi/
├── KS.CFG                    # Your kickstart config (ks-esx01.cfg)
├── EFI/
│   └── BOOT/
│       ├── BOOT.CFG          # Modified to use kickstart
│       └── BOOT.CFG.backup   # Original saved
├── b.b00                     # ESXi installer files
├── jumpstrt.gz
├── ... (all ESXi ISO files)
```

**USB Usage:**

1. Insert USB into MS-A2 host
2. Power on host
3. Press F11 (or boot menu key)
4. Select USB device
5. Installation proceeds **automatically** (no user interaction)
6. Host reboots twice (initial install + firstboot configuration)
7. ESXi ready at configured IP (e.g., 172.30.0.10)

---

### Step 4: Install ESXi on Physical Hosts

**Process:** Boot from USB created in Step 3

**What Happens Automatically:**

#### 4.1 Initial ESXi Installation (Reboot 1)

```
1. Boot from USB
2. ESXi installer reads KS.CFG from USB
3. Installs ESXi to specified NVMe disk
4. Sets root password
5. Configures network (IP, gateway, VLAN)
6. Sets hostname
7. First reboot
```

#### 4.2 Firstboot Configuration (Reboot 2)

```
8. ESXi boots for first time
9. Runs %firstboot section from kickstart
10. Configures:
    - NTP servers
    - DNS servers
    - vSwitch0 with MTU 9000
    - NVMe tiering for vSAN ESA
    - Local VMFS datastore
    - SSH/ESXi Shell (enabled)
    - Firewall rules
11. Second reboot
```

#### 4.3 Final State

```
12. ESXi fully configured and running
13. Accessible via:
    - https://172.30.0.10 (or .11, .12)
    - https://esx01.vcf.lab (or esx02, esx03)
14. SSH enabled on port 22
15. Ready for VCF Installer deployment
```

**Verification:**

```bash
# From your management system
ping 172.30.0.10
ping 172.30.0.11
ping 172.30.0.12

# SSH to each host (verify SSH enabled)
ssh root@172.30.0.10  # Password: VMware1!

# Verify ESXi version (MUST be 9.0.0.0 build 24755229)
ssh root@172.30.0.10 "vmware -v"
# Output: VMware ESXi 9.0.0 build-24755229

# Verify NVMe tiering configured
ssh root@172.30.0.10 "esxcli nvme device list"

# Verify datastore created
ssh root@172.30.0.10 "esxcli storage filesystem list"
```

**Result:** Three ESXi hosts ready for VCF deployment:

- esx01.vcf.lab (172.30.0.10) ✓
- esx02.vcf.lab (172.30.0.11) ✓
- esx03.vcf.lab (172.30.0.12) ✓

---

### Step 5: Deploy VCF Installer Appliance

**Script:** `scripts/deploy_vcf_installer.sh`

**What It Does:**

1. Uses OVFTool to deploy VCF Installer OVA
2. Deploys to one of the ESXi hosts (typically esx01)
3. Configures networking for VCF Installer
4. Powers on the VM

**Why This Step:**

- VCF Installer is a **VM appliance** (not installed on bare metal)
- Needs to run on one of the ESXi hosts
- Acts as orchestrator for entire VCF deployment
- This is why **ESXi must be installed first** (chicken/egg)

**How It Works:**

```
Prerequisites:
  - ESXi 9.0.0.0 running on esx01 (172.30.0.10)
  - SSH enabled on esx01
  - VCF Installer OVA downloaded
  - OVFTool installed locally

Process:
  1. OVFTool connects to esx01 via SSH
  2. Uploads VCF Installer OVA
  3. Deploys as VM on esx01
  4. Configures VM properties:
     - IP: 172.30.0.21
     - Gateway: 172.30.0.1
     - DNS: 192.168.10.2
     - Hostname: sddcm01.vcf.lab
     - Root password
     - Admin password
  5. Powers on VM
  6. Waits for VM to boot (~5 minutes)

Result:
  - VCF Installer VM running at 172.30.0.21
  - Accessible via https://172.30.0.21 or https://sddcm01.vcf.lab
```

**Commands:**

```bash
# Edit script first (lines 19-35)
vim scripts/deploy_vcf_installer.sh

# Variables to configure:
ESXI_HOST="172.30.0.10"          # Which ESXi host to deploy to
ESXI_USERNAME="root"
ESXI_PASSWORD="VMware1!"
VCFI_IP="172.30.0.21"            # VCF Installer IP
VCFI_GATEWAY="172.30.0.1"
VCFI_DNS="192.168.10.2"
VCFI_HOSTNAME="sddcm01.vcf.lab"
VCFI_ROOT_PASSWORD="VMware1!VMware1!"
VCFI_ADMIN_PASSWORD="VMware1!VMware1!"
OVA_PATH="/path/to/VCF-SDDC-Manager-Appliance-9.0.0.0.24703748.ova"
DATASTORE="local-vmfs-datastore-1"  # Created by kickstart
NETWORK="VM Network"                 # ESXi port group

# Run deployment
cd scripts
chmod +x deploy_vcf_installer.sh
./deploy_vcf_installer.sh
```

**Input Files:**

- VCF Installer OVA: `VCF-SDDC-Manager-Appliance-9.0.0.0.24703748.ova`
- Target ESXi host: `esx01.vcf.lab` (172.30.0.10)

**Output:**

- VCF Installer VM running at 172.30.0.21
- UI accessible at <https://sddcm01.vcf.lab>

**Verification:**

```bash
# Ping VCF Installer
ping 172.30.0.21

# Check if web UI is up (may take 5-10 minutes)
curl -k https://172.30.0.21

# SSH to VCF Installer
ssh root@172.30.0.21  # Password: VMware1!VMware1!

# From ESXi host, verify VM is running
ssh root@172.30.0.10
vim-cmd vmsvc/getallvms | grep -i sddc
vim-cmd vmsvc/power.getstate <vmid>
```

---

### Step 6: Configure VCF Installer

**Script:** `scripts/setup_vcf_installer.ps1`

**What It Does:**

1. Connects to VCF Installer via API
2. Configures offline depot settings
3. Disables HTTPS requirement (HTTP OK for lab)
4. Prepares VCF Installer for deployment

**Why This Step:**

- VCF Installer needs to know where to find binaries (Offline Depot)
- By default requires HTTPS, but lab setups often use HTTP
- Some settings can't be changed via UI, require API calls

**How It Works:**

```powershell
Process:
  1. Import PowerCLI module
  2. Connect to VCF Installer at 172.30.0.21
  3. Authenticate with admin@local credentials
  4. Configure:
     - Offline depot URL (http://your-server/VCF/PROD)
     - Disable HTTPS requirement
     - Set download paths
  5. Test connection to depot
  6. Verify configuration

Result:
  - VCF Installer ready to connect to offline depot
  - Ready to download binaries
  - Ready for VCF deployment
```

**Commands:**

```powershell
# Edit script first (lines 10-15)
# Set:
$vcfInstallerFQDN = "sddcm01.vcf.lab"
$vcfInstallerAdmin = "admin@local"
$vcfInstallerPassword = "VMware1!VMware1!"
$offlineDepotUrl = "http://your-nas.lab/vcf-depot/PROD"

# Run configuration
cd scripts
pwsh ./setup_vcf_installer.ps1
```

**Input:**

- VCF Installer at 172.30.0.21
- Admin credentials
- Offline Depot URL

**Output:**

- VCF Installer configured and ready
- Can now connect to depot and download binaries

---

### Step 7: Deploy VCF Management Domain

**Process:** Manual via VCF Installer UI

**What Happens:**

#### 7.1 Connect to Offline Depot (via UI)

```
1. Login to https://sddcm01.vcf.lab
   - Username: admin@local
   - Password: VMware1!VMware1!

2. Click "DEPOT SETTINGS AND BINARY MANAGEMENT"

3. Connect to offline depot:
   - URL: http://your-nas.lab/vcf-depot/PROD
   - Should show "Active" status

4. Click "DOWNLOAD" button
   - Downloads all VCF binaries:
     * vCenter Server 9.0
     * NSX-T 9.0
     * VCF Operations
     * vSAN components
   - Wait ~30-60 minutes depending on network speed

5. Verify all downloads show "Success"
```

#### 7.2 Upload VCF Deployment Manifest

```
6. Return to VCF Installer homepage

7. Click "DEPLOY USING JSON SPEC"

8. Choose manifest:
   - Two-node: config/vcf90-two-node.json
   - Three-node: config/vcf90-three-node.json (recommended)

9. Upload manifest file

10. Click "Next" to start validation

11. Review pre-check results:
    - Some warnings are expected (MTU validation on MikroTik)
    - Critical errors must be fixed
    - Acknowledge warnings if configuration is correct

12. Click "DEPLOY" to start deployment
```

**What The Manifest Contains:**

```json
{
  "workflowType": "VCF",
  "version": "9.0.0.0",
  "hostSpecs": [
    {"hostname": "esx01", ...},  // References ESXi hosts
    {"hostname": "esx02", ...},  // deployed in Step 4
    {"hostname": "esx03", ...}
  ],
  "vcenterSpec": {
    "vcenterHostname": "vc01",
    "vmSize": "small",
    ...
  },
  "nsxtSpec": {
    "nsxtManagers": [{"hostname": "nsx01a"}],
    ...
  },
  "networkSpecs": [
    {"networkType": "MANAGEMENT", "vlanId": "30", ...},
    {"networkType": "VMOTION", "vlanId": "40", ...},
    {"networkType": "VSAN", "vlanId": "50", ...}
  ]
}
```

#### 7.3 VCF Deployment Process (3-4 hours)

```
Deployment Phases:

Phase 1: Validation
  - Verify ESXi hosts reachable
  - Check network connectivity
  - Validate DNS entries
  - Verify VLAN configuration
  - Check storage availability

Phase 2: vCenter Deployment
  - Deploy vCenter Server VM
  - Configure SSO (vsphere.local)
  - Add ESXi hosts to vCenter
  - Create datacenter and cluster

Phase 3: vSAN Configuration
  - Create vSAN cluster
  - Configure vSAN ESA
  - Claim NVMe devices
  - Create vSAN datastore

Phase 4: NSX-T Deployment
  - Deploy NSX Manager VM
  - Configure NSX Manager
  - Install NSX on ESXi hosts
  - Configure transport zones
  - Create TEP interfaces

Phase 5: VDS Configuration
  - Create vSphere Distributed Switch
  - Configure port groups
  - Configure uplinks
  - Migrate management vmkernel

Phase 6: VCF Operations
  - Deploy vROps VM
  - Deploy vRA VM
  - Deploy vRSLCM VM
  - Deploy Cloud Proxy
  - Deploy Automation

Phase 7: Finalization
  - Register all components
  - Configure monitoring
  - Run health checks
  - Complete deployment
```

#### 7.4 Two-Node Specific: Storage Policy Fix

```
IF using vcf90-two-node.json:

  IMMEDIATELY after clicking "DEPLOY", run:

  pwsh scripts/fix_vsan_esa_default_storage_policy.ps1

  Why:
  - Default vSAN policy requires 3 hosts (FTT=1)
  - Two-node needs different policy (FTT=0)
  - Script waits for vCenter, then auto-fixes policy
  - Prevents deployment failure

IF using vcf90-three-node.json:

  No action needed - standard vSAN policy works
```

#### 7.5 Monitoring Deployment

```
Monitor progress via VCF Installer UI:
  - Shows current phase
  - Shows task progress
  - Shows logs for troubleshooting
  - Estimated time remaining

SSH to VCF Installer for detailed logs:
  ssh root@172.30.0.21
  tail -f /var/log/vmware/vcf/bringup/vcf-bringup.log
```

---

## File Dependencies

### Configuration Flow

```
config/vcf-config.yaml                    # Source of truth
    ↓
scripts/generate_kickstart.py             # Reads YAML
    ↓
config/ks-esx01.cfg                       # Generated kickstart
config/ks-esx02.cfg
config/ks-esx03.cfg
    ↓
scripts/create_esxi_usb.py                # Embeds kickstart in USB
    ↓
USB Drive with KS.CFG                     # Bootable installer
    ↓
ESXi Installed on MS-A2                   # Physical hosts ready
    ↓
scripts/deploy_vcf_installer.sh           # Deploys on ESXi
    ↓
VCF Installer VM at 172.30.0.21          # Orchestrator ready
    ↓
scripts/setup_vcf_installer.ps1           # Configures orchestrator
    ↓
config/vcf90-three-node.json              # Deployment manifest
    ↓
VCF Management Domain Deployed            # Complete VCF environment
```

### File Types and Purpose

| File Type | Purpose | Created By | Used By |
|-----------|---------|------------|---------|
| `vcf-config.yaml` | Master configuration | User (manually edit) | `generate_kickstart.py`, `create_esxi_usb.py` |
| `ks-template.cfg.j2` | Kickstart template | Project (version control) | `generate_kickstart.py` |
| `ks-esx0X.cfg` | ESXi kickstart configs | `generate_kickstart.py` | `create_esxi_usb.py` |
| USB Drive | Bootable ESXi installer | `create_esxi_usb.py` | Physical host (boot) |
| ESXi Hosts | Running infrastructure | USB installer | `deploy_vcf_installer.sh` |
| VCF Installer OVA | Orchestrator appliance | VMware (download) | `deploy_vcf_installer.sh` |
| VCF Installer VM | Running orchestrator | `deploy_vcf_installer.sh` | `setup_vcf_installer.ps1`, VCF deployment |
| `vcf90-three-node.json` | VCF manifest | Project (customize) | VCF Installer (deployment) |

---

## Troubleshooting

### Finding NVMe Identifiers

**Problem:** Don't know NVMe device identifiers for kickstart config

**Solution:**

1. Create basic USB with ESXi ISO (without kickstart)
2. Boot MS-A2 from USB
3. Press ALT+F1 at ESXi installer screen
4. Login as `root` (blank password, just press Enter)
5. Enable SSH: `/etc/init.d/SSH start`
6. Note IP address shown on screen
7. From another computer: `ssh root@<ip-address>`
8. Run: `vdq -q`
9. Note device identifiers like `t10.NVMe____Samsung_SSD_980_500GB___...`
10. Update in `config/vcf-config.yaml`

### Common Issues

#### Issue: Kickstart generation fails

```bash
# Check YAML syntax
uv run python -c "import yaml; yaml.safe_load(open('config/vcf-config.yaml'))"

# Run in verbose mode
uv run scripts/generate_kickstart.py all -v
```

#### Issue: USB creation fails with permission error

```bash
# Must use sudo
sudo make usb-create USB=/dev/disk2 HOST=1

# Or verify you're using the right device
make usb-list
```

#### Issue: ESXi doesn't boot from USB

```bash
# Verify BOOT.CFG was modified
# Mount USB and check:
cat /Volumes/ESXi/EFI/BOOT/BOOT.CFG | grep kernelopt
# Should show: kernelopt=ks=usb:/KS.CFG
```

#### Issue: Kickstart doesn't run (interactive install starts)

```bash
# Verify KS.CFG exists on USB root
ls /Volumes/ESXi/KS.CFG

# Verify BOOT.CFG points to it
cat /Volumes/ESXi/EFI/BOOT/BOOT.CFG | grep "ks=usb"
```

#### Issue: VCF Installer deployment fails

```bash
# Verify ESXi version
ssh root@172.30.0.10 "vmware -v"
# MUST show: VMware ESXi 9.0.0 build-24755229

# Verify SSH enabled on ESXi
ssh root@172.30.0.10 "esxcli system settings advanced list -o /UserVars/SuppressShellWarning"

# Verify datastore exists
ssh root@172.30.0.10 "esxcli storage filesystem list"
```

#### Issue: VCF deployment validation fails

```bash
# Check DNS resolution
nslookup esx01.vcf.lab 192.168.10.2
nslookup esx02.vcf.lab 192.168.10.2
nslookup esx03.vcf.lab 192.168.10.2

# Check VLAN configuration on switch
# Verify VLANs 30, 40, 50, 60 are created and trunked

# Check ESXi network connectivity
ssh root@172.30.0.10 "esxcfg-vswitch -l"
ssh root@172.30.0.10 "esxcfg-vmknic -l"
```

---

## Summary

### Complete Command Sequence

```bash
# 1. Configure (manual)
vim config/vcf-config.yaml

# 2. Generate kickstart configs
make generate

# 3. Create USB installers (one USB, reused for each host)
sudo make usb-create USB=/dev/disk2 HOST=1
# ... insert USB in host 1, boot, wait for install ...
sudo make usb-create USB=/dev/disk2 HOST=2
# ... insert USB in host 2, boot, wait for install ...
sudo make usb-create USB=/dev/disk2 HOST=3
# ... insert USB in host 3, boot, wait for install ...

# 4. Verify ESXi installed
ssh root@172.30.0.10 "vmware -v"
ssh root@172.30.0.11 "vmware -v"
ssh root@172.30.0.12 "vmware -v"

# 5. Deploy VCF Installer
cd scripts
vim deploy_vcf_installer.sh  # Edit variables
./deploy_vcf_installer.sh

# 6. Configure VCF Installer
vim setup_vcf_installer.ps1  # Edit variables
pwsh ./setup_vcf_installer.ps1

# 7. Deploy VCF (via UI)
# - Login to https://sddcm01.vcf.lab
# - Connect to offline depot
# - Download binaries
# - Upload manifest (config/vcf90-three-node.json)
# - Start deployment

# 8. Monitor deployment (3-4 hours)
ssh root@172.30.0.21
tail -f /var/log/vmware/vcf/bringup/vcf-bringup.log
```

### Time Estimates

| Step | Duration | Parallelizable |
|------|----------|----------------|
| Configure YAML | 15 min | - |
| Generate kickstart | <1 min | - |
| Create USB (per host) | 5-10 min | No (same USB) |
| Install ESXi (per host) | 15-20 min | Yes (3 USB drives) |
| Deploy VCF Installer | 10 min | - |
| Configure VCF Installer | 5 min | - |
| Download binaries | 30-60 min | - |
| VCF deployment | 3-4 hours | - |
| **Total** | **~5-6 hours** | |

### Key Takeaways

1. **Everything starts with YAML** - Single source of truth
2. **Scripts are chained** - Each depends on previous output
3. **ESXi version is critical** - MUST be 9.0.0.0 build 24755229
4. **Order matters** - Can't skip steps or reorder
5. **Automation reduces errors** - Kickstart + scripts = consistent deployments
6. **VCF Installer is orchestrator** - Handles complex deployment
7. **Monitoring is important** - Check logs during deployment

---

**Last Updated:** October 16, 2024
