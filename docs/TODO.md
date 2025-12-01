# TODO List

- [x] Delete any VMs on the `MS-A2-Cluster` cluster.
- [x] Provision TKGI on `NUC-Cluster` cluster.
- [x] Change Mgmt subnet from `171.30.30.0/24` to `171.30.0.0/24` subnet.
- [x] Update static route for "VCF Mgmt Network" Next Hop Destination from `171.30.30.0/24` to `171.30.0.0/24`.
- [x] Move Mikrotik uplink ethernet5 to `USW-Lite-16-PoE` switch.
- [x] Update the switch profile for the port on the `USW-Lite-16-PoE` switch to be used for the uplink from the `MikroTik CRS304-4XG-IN` switch.
- [x] Make sure switch port is configured for jumbo frames
- [x] Setup Pihole Unbound for DNS.
- [x] Recreate or migrate the Pihole/DNS VM to a different host
- [x] Update PiHole conf and set the dns.vcf.lab record to 192.168.10.2.
- [x] Update DNS records in [DNS Policy Table](https://192.168.2.231/network/default/settings/policy-table?preset=dns-records).
- [x] Create a bootable usb drive with ESXi 9.
- [x] Install ESXi 9 on all 3 esxi-ms-a2-XX hosts.
- [x] Run the VCF Installer
- [x] Install Licenses in [VCF Operations instance](https://vcf01.vcf.lab)
- [x] Configure [NSX Virtual Private Cloud (VPC)](https://williamlam.com/2025/07/ms-a2-vcf-9-0-lab-configuring-nsx-virtual-private-cloud-vpc.html)
- [x] Configure [vSphere Supervisor with NSX VPC Networking](https://williamlam.com/2025/08/ms-a2-vcf-9-0-lab-configuring-vsphere-supervisor-with-nsx-vpc-networking.html)
- [x] Configure [VCF Automation](https://williamlam.com/2025/08/ms-a2-vcf-9-0-lab-configuring-vcf-automation.html)
