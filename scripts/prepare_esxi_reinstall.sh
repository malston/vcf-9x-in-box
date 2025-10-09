#!/bin/bash
# Author: Automated ESXi Reinstallation Preparation Script
# Purpose: Prepare kickstart configs and USB installer for ESXi reinstallation on new network

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration Variables - CUSTOMIZE THESE
ESXI_ISO_PATH="$HOME/Storage/Software/VCF9/PROD/COMP/ESX_HOST/VMware-VMvisor-Installer-9.0.0.0.24755229.x86_64.iso"
WORKING_DIR="./esxi-reinstall-temp"

# Network Configuration for New Setup
NEW_NETWORK="172.30.0.0/24"
NEW_GATEWAY="172.30.0.1"
NEW_VLAN="30"
NEW_DNS="172.30.0.2"  # Update this if using different DNS
NEW_DOMAIN="vcf.lab"
NTP_SERVER="pool.ntp.org"

# ESXi Host 1 Configuration
ESX01_IP="172.30.0.10"
ESX01_HOSTNAME="esx01.vcf.lab"

# ESXi Host 2 Configuration
ESX02_IP="172.30.0.11"
ESX02_HOSTNAME="esx02.vcf.lab"

# Root Password
ROOT_PASSWORD="VMware1!"

# NVMe Device Identifiers - MUST BE CUSTOMIZED FOR YOUR HARDWARE
# Run 'vdq -q' on ESXi console to find these values
ESX01_INSTALL_DISK="t10.NVMe____Samsung_SSD_980_500GB___________________7F17A051D3382500"  # Boot/Install disk for ESX01
ESX02_INSTALL_DISK="t10.NVMe____Samsung_SSD_980_500GB___________________9E17A051D3382500"  # Boot/Install disk for ESX02

ESX01_TIERING_DISK="t10.NVMe____Samsung_SSD_990_PRO_4TB_________________72A9415145382500"  # NVMe Tiering disk for ESX01
ESX02_TIERING_DISK="t10.NVMe____Samsung_SSD_990_PRO_4TB_________________84A9415145382500"  # NVMe Tiering disk for ESX02

# SSH Public Key (optional - leave empty if not using)
SSH_ROOT_KEY=""

################################################################################
# DO NOT EDIT BELOW THIS LINE
################################################################################

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}ESXi Reinstallation Preparation Script${NC}"
echo -e "${GREEN}========================================${NC}\n"

# Check if ESXi ISO exists
if [[ ! -f "$ESXI_ISO_PATH" ]]; then
    echo -e "${RED}ERROR: ESXi ISO not found at: $ESXI_ISO_PATH${NC}"
    echo "Please update ESXI_ISO_PATH variable in the script"
    exit 1
fi

echo -e "${GREEN}✓${NC} Found ESXi ISO: $ESXI_ISO_PATH\n"

# Create working directory
echo -e "${YELLOW}Creating working directory...${NC}"
mkdir -p "$WORKING_DIR"

# Generate kickstart config for ESX01
echo -e "${YELLOW}Generating kickstart config for ESX01...${NC}"
cat > "$WORKING_DIR/ks-esx01.cfg" <<EOF
vmaccepteula
install --disk=${ESX01_INSTALL_DISK} --overwritevmfs
reboot

network --bootproto=static --vlanid=${NEW_VLAN} --ip=${ESX01_IP} --netmask=255.255.255.0 --gateway=${NEW_GATEWAY} --hostname=${ESX01_HOSTNAME} --nameserver=${NEW_DNS} --addvmportgroup=1
rootpw ${ROOT_PASSWORD}

%firstboot --interpreter=busybox

NVME_TIERING_DEVICE="${ESX01_TIERING_DISK}"
VMFS_DATASTORE_NAME="local-vmfs-datastore-1"
NTP_SERVER=${NTP_SERVER}
SSH_ROOT_KEY="${SSH_ROOT_KEY}"
MANAGEMENT_VLAN=${NEW_VLAN}
MANAGEMENT_VSWITCH_MTU=9000

# Ensure hostd is ready
while ! vim-cmd hostsvc/runtimeinfo; do
sleep 10
done

# enable & start SSH
vim-cmd hostsvc/enable_ssh
vim-cmd hostsvc/start_ssh

# enable & start ESXi Shell
vim-cmd hostsvc/enable_esx_shell
vim-cmd hostsvc/start_esx_shell

# Suppress ESXi Shell warning
esxcli system settings advanced set -o /UserVars/SuppressShellWarning -i 1

# Configure NTP
esxcli system ntp set -e true -s \$NTP_SERVER

# Rename local VMFS datastore
vim-cmd hostsvc/datastore/rename datastore1 \${VMFS_DATASTORE_NAME}

# Enable & Configure NVMe Tiering
esxcli system settings kernel set -s MemoryTiering -v TRUE
esxcli system settings advanced set -o /Mem/TierNvmePct -i 100
esxcli system tierdevice create -d /vmfs/devices/disks/\${NVME_TIERING_DEVICE}

/bin/generate-certificates

# Workaround required for AMD Ryzen-based CPU
echo 'monitor_control.disable_apichv ="TRUE"' >> /etc/vmware/config

# Install vSAN ESA Mock VIB
esxcli network firewall ruleset set -e true -r httpClient
esxcli software acceptance set --level CommunitySupported
esxcli software vib install -v https://github.com/lamw/nested-vsan-esa-mock-hw-vib/releases/download/1.0/nested-vsan-esa-mock-hw.vib --no-sig-check
esxcli network firewall ruleset set -e false -r httpClient

# Configure SSH keys if provided
if [ -n "\${SSH_ROOT_KEY}" ]; then
    echo "\${SSH_ROOT_KEY}" > /etc/ssh/keys-root/authorized_keys
fi

# Configure VM Network VLAN & MTU
esxcli network vswitch standard portgroup set -p "VM Network" -v \${MANAGEMENT_VLAN}
esxcli network vswitch standard set -m \${MANAGEMENT_VSWITCH_MTU} -v vSwitch0

reboot
EOF

echo -e "${GREEN}✓${NC} Created: $WORKING_DIR/ks-esx01.cfg"

# Generate kickstart config for ESX02
echo -e "${YELLOW}Generating kickstart config for ESX02...${NC}"
cat > "$WORKING_DIR/ks-esx02.cfg" <<EOF
vmaccepteula
install --disk=${ESX02_INSTALL_DISK} --overwritevmfs
reboot

network --bootproto=static --vlanid=${NEW_VLAN} --ip=${ESX02_IP} --netmask=255.255.255.0 --gateway=${NEW_GATEWAY} --hostname=${ESX02_HOSTNAME} --nameserver=${NEW_DNS} --addvmportgroup=1
rootpw ${ROOT_PASSWORD}

%firstboot --interpreter=busybox

NVME_TIERING_DEVICE="${ESX02_TIERING_DISK}"
VMFS_DATASTORE_NAME="local-vmfs-datastore-2"
NTP_SERVER=${NTP_SERVER}
SSH_ROOT_KEY="${SSH_ROOT_KEY}"
MANAGEMENT_VLAN=${NEW_VLAN}
MANAGEMENT_VSWITCH_MTU=9000

# Ensure hostd is ready
while ! vim-cmd hostsvc/runtimeinfo; do
sleep 10
done

# enable & start SSH
vim-cmd hostsvc/enable_ssh
vim-cmd hostsvc/start_ssh

# enable & start ESXi Shell
vim-cmd hostsvc/enable_esx_shell
vim-cmd hostsvc/start_esx_shell

# Suppress ESXi Shell warning
esxcli system settings advanced set -o /UserVars/SuppressShellWarning -i 1

# Configure NTP
esxcli system ntp set -e true -s \$NTP_SERVER

# Rename local VMFS datastore
vim-cmd hostsvc/datastore/rename datastore1 \${VMFS_DATASTORE_NAME}

# Enable & Configure NVMe Tiering
esxcli system settings kernel set -s MemoryTiering -v TRUE
esxcli system settings advanced set -o /Mem/TierNvmePct -i 100
esxcli system tierdevice create -d /vmfs/devices/disks/\${NVME_TIERING_DEVICE}

/bin/generate-certificates

# Workaround required for AMD Ryzen-based CPU
echo 'monitor_control.disable_apichv ="TRUE"' >> /etc/vmware/config

# Install vSAN ESA Mock VIB
esxcli network firewall ruleset set -e true -r httpClient
esxcli software acceptance set --level CommunitySupported
esxcli software vib install -v https://github.com/lamw/nested-vsan-esa-mock-hw-vib/releases/download/1.0/nested-vsan-esa-mock-hw.vib --no-sig-check
esxcli network firewall ruleset set -e false -r httpClient

# Configure SSH keys if provided
if [ -n "\${SSH_ROOT_KEY}" ]; then
    echo "\${SSH_ROOT_KEY}" > /etc/ssh/keys-root/authorized_keys
fi

# Configure VM Network VLAN & MTU
esxcli network vswitch standard portgroup set -p "VM Network" -v \${MANAGEMENT_VLAN}
esxcli network vswitch standard set -m \${MANAGEMENT_VSWITCH_MTU} -v vSwitch0

reboot
EOF

echo -e "${GREEN}✓${NC} Created: $WORKING_DIR/ks-esx02.cfg"

# Also update the config directory files
echo -e "${YELLOW}Updating config directory files...${NC}"
cp "$WORKING_DIR/ks-esx01.cfg" "../config/ks-esx01.cfg"
cp "$WORKING_DIR/ks-esx02.cfg" "../config/ks-esx02.cfg"
echo -e "${GREEN}✓${NC} Updated config/ks-esx01.cfg and config/ks-esx02.cfg"

# Create BOOT.CFG template
echo -e "${YELLOW}Creating BOOT.CFG template...${NC}"
cat > "$WORKING_DIR/BOOT.CFG.template" <<'EOF'
bootstate=0
title=Loading ESXi installer
timeout=5
prefix=
kernel=/b.b00
kernelopt=ks=usb:/KS.CFG
modules=/jumpstrt.gz --- /useropts.gz --- /features.gz --- /k.b00 --- /uc_intel.b00 --- /uc_amd.b00 --- /uc_hygon.b00 --- /procfs.b00 --- /vmx.v00 --- /vim.v00 --- /tpm.v00 --- /sb.v00 --- /s.v00 --- /atlantic.v00 --- /bcm_mpi3.v00 --- /bnxtnet.v00 --- /bnxtroce.v00 --- /brcmfcoe.v00 --- /cndi_igc.v00 --- /dwi2c.v00 --- /elxiscsi.v00 --- /elxnet.v00 --- /i40en.v00 --- /iavmd.v00 --- /icen.v00 --- /igbn.v00 --- /intelgpi.v00 --- /ionic_cl.v00 --- /ionic_en.v00 --- /irdman.v00 --- /iser.v00 --- /ixgben.v00 --- /lpfc.v00 --- /lpnic.v00 --- /lsi_mr3.v00 --- /lsi_msgp.v00 --- /lsi_msgp.v01 --- /lsi_msgp.v02 --- /mtip32xx.v00 --- /ne1000.v00 --- /nenic.v00 --- /nfnic.v00 --- /nhpsa.v00 --- /nipmi.v00 --- /nmlx5_cc.v00 --- /nmlx5_co.v00 --- /nmlx5_rd.v00 --- /ntg3.v00 --- /nvme_pci.v00 --- /nvmerdma.v00 --- /nvmetcp.v00 --- /nvmxnet3.v00 --- /nvmxnet3.v01 --- /pvscsi.v00 --- /qcnic.v00 --- /qedentv.v00 --- /qedrntv.v00 --- /qfle3.v00 --- /qfle3f.v00 --- /qfle3i.v00 --- /qflge.v00 --- /rdmahl.v00 --- /rshim_ne.v00 --- /rshim.v00 --- /rste.v00 --- /sfvmk.v00 --- /smartpqi.v00 --- /vmkata.v00 --- /vmksdhci.v00 --- /vmkusb.v00 --- /vmw_ahci.v00 --- /bmcal.v00 --- /clusters.v00 --- /crx.v00 --- /drivervm.v00 --- /elx_esx_.v00 --- /btldr.v00 --- /dvfilter.v00 --- /esx_ui.v00 --- /esxupdt.v00 --- /tpmesxup.v00 --- /weaselin.v00 --- /esxio_co.v00 --- /infravis.v00 --- /loadesx.v00 --- /lsuv2_hp.v00 --- /lsuv2_in.v00 --- /lsuv2_ls.v00 --- /lsuv2_nv.v00 --- /lsuv2_oe.v00 --- /lsuv2_oe.v01 --- /lsuv2_sm.v00 --- /native_m.v00 --- /qlnative.v00 --- /trx.v00 --- /vcls_pod.v00 --- /vdfs.v00 --- /vds_vsip.v00 --- /vmware_e.v00 --- /hbrsrv.v00 --- /vsan.v00 --- /vsanheal.v00 --- /vsanmgmt.v00 --- /tools.t00 --- /xorg.v00 --- /gc.v00 --- /imgdb.tgz --- /basemisc.tgz --- /resvibs.tgz --- /esxiodpt.tgz --- /imgpayld.tgz
build=8.0.3-0.35.24280767
updated=0
EOF

echo -e "${GREEN}✓${NC} Created: $WORKING_DIR/BOOT.CFG.template"

# Create installation instructions
cat > "$WORKING_DIR/INSTALLATION_INSTRUCTIONS.md" <<'EOF'
# ESXi Reinstallation Instructions

## Prerequisites
- 2 USB drives (16GB or larger) - one for each host
- UNetbootin (https://unetbootin.github.io/) or similar bootable USB creator
- ESXi ISO file

## Step 1: Create Bootable USB Drive

### For macOS/Linux:
1. Download and install UNetbootin
2. Insert USB drive
3. Open UNetbootin
4. Select "Diskimage" and browse to the ESXi ISO
5. Select your USB drive
6. Click OK and wait for completion

### Alternative (macOS only):
```bash
# Find USB drive identifier
diskutil list

# Unmount USB (replace diskX with your USB identifier)
diskutil unmountDisk /dev/diskX

# Write ISO to USB (replace diskX with your USB identifier)
sudo dd if=/path/to/esxi.iso of=/dev/rdiskX bs=1m

# Eject USB
diskutil eject /dev/diskX
```

## Step 2: Modify USB Drive for Kickstart Installation

After creating the bootable USB:

1. **Copy kickstart config to USB root:**
   - For ESX01: Copy `ks-esx01.cfg` to USB and rename to `KS.CFG` (all caps)
   - For ESX02: Copy `ks-esx02.cfg` to USB and rename to `KS.CFG` (all caps)

2. **Modify BOOT.CFG on USB:**
   - Navigate to `EFI/BOOT/` on the USB drive
   - Edit `BOOT.CFG` file
   - Update the `kernelopt` line to: `kernelopt=ks=usb:/KS.CFG`
   - Save the file

   The complete BOOT.CFG should look like the BOOT.CFG.template file in this directory.

## Step 3: Boot and Install

For each ESXi host:

1. **Backup any critical data** (installation will WIPE the host!)
2. Insert USB drive into the MS-A2 system
3. Power on and enter BIOS/UEFI boot menu (usually F11 or F12)
4. Select USB drive as boot device
5. ESXi installer will boot automatically
6. You may see a warning - press Enter or wait to continue
7. Installation will proceed automatically (no interaction needed)
8. Host will reboot twice:
   - First reboot: After initial ESXi installation
   - Second reboot: After firstboot script completes configuration
9. After final reboot, the host should be accessible at:
   - ESX01: https://172.30.0.10 or https://esx01.vcf.lab
   - ESX02: https://172.30.0.11 or https://esx02.vcf.lab

## Step 4: Verify Installation

Login to each host via web UI or SSH:
- Username: `root`
- Password: `VMware1!`

Verify:
- Hostname is correct (esx01.vcf.lab or esx02.vcf.lab)
- IP address is correct (172.30.0.10 or 172.30.0.11)
- VLAN 30 is configured on management network
- DNS resolution works
- NTP is configured and syncing
- SSH is enabled
- vSAN ESA Mock VIB is installed

## Troubleshooting

**Problem: Installation fails to start**
- Check that BOOT.CFG was modified correctly
- Verify KS.CFG is in the root of the USB drive (not in a subdirectory)

**Problem: Can't identify NVMe device labels**
- Boot ESXi installer without kickstart (remove KS.CFG reference from BOOT.CFG)
- Press ALT+F1 to access console
- Login as root (blank password)
- Run: `/etc/init.d/SSH start`
- SSH to the host and run: `vdq -q`
- Note the device identifiers and update the script variables

**Problem: Host not reachable after installation**
- Verify MikroTik switch has VLAN 30 configured
- Check that the network cable is connected to correct port
- Verify gateway 172.30.0.1 is reachable from VLAN 30
- Check DNS server is accessible

## Network Requirements

Ensure your MikroTik CRS304-4XG-IN has:
- VLAN 30 configured and tagged on appropriate ports
- Gateway 172.30.0.1 accessible on VLAN 30
- DNS server (172.30.0.2 or as configured) reachable
- Jumbo frames (MTU 9000) enabled if desired

EOF

echo -e "${GREEN}✓${NC} Created: $WORKING_DIR/INSTALLATION_INSTRUCTIONS.md"

# Summary
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Preparation Complete!${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo -e "Configuration Summary:"
echo -e "  Network:     ${NEW_NETWORK}"
echo -e "  Gateway:     ${NEW_GATEWAY}"
echo -e "  VLAN:        ${NEW_VLAN}"
echo -e "  DNS Server:  ${NEW_DNS}"
echo -e "  DNS Domain:  ${NEW_DOMAIN}"
echo -e ""
echo -e "  ESX01 IP:    ${ESX01_IP}"
echo -e "  ESX01 FQDN:  ${ESX01_HOSTNAME}"
echo -e ""
echo -e "  ESX02 IP:    ${ESX02_IP}"
echo -e "  ESX02 FQDN:  ${ESX02_HOSTNAME}"
echo -e ""

echo -e "Generated files in ${YELLOW}${WORKING_DIR}/${NC}:"
echo -e "  - ks-esx01.cfg (kickstart config for host 1)"
echo -e "  - ks-esx02.cfg (kickstart config for host 2)"
echo -e "  - BOOT.CFG.template (template for USB boot config)"
echo -e "  - INSTALLATION_INSTRUCTIONS.md (step-by-step guide)"
echo -e ""

echo -e "${YELLOW}Next Steps:${NC}"
echo -e "1. Review the generated kickstart configs in ${WORKING_DIR}/"
echo -e "2. Verify NVMe device identifiers match your hardware"
echo -e "3. Read ${WORKING_DIR}/INSTALLATION_INSTRUCTIONS.md for USB preparation"
echo -e "4. Create bootable USB drives using UNetbootin"
echo -e "5. Follow the installation instructions to reinstall each host"
echo -e ""

echo -e "${YELLOW}IMPORTANT:${NC}"
echo -e "  - Installation will ${RED}WIPE ALL DATA${NC} on the ESXi hosts!"
echo -e "  - Verify NVMe device identifiers before proceeding"
echo -e "  - Ensure VLAN 30 is configured on your MikroTik switch"
echo -e "  - Test connectivity to gateway ${NEW_GATEWAY} from VLAN 30"
echo -e ""

echo -e "${GREEN}Configuration files also copied to:${NC}"
echo -e "  - config/ks-esx01.cfg"
echo -e "  - config/ks-esx02.cfg"
echo -e ""
