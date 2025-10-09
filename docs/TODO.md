# TODO List

- [x] Delete any VMs on the `MS-A2-Cluster` cluster.
- [x] Provision TKGI on `NUC-Cluster` cluster.
- [x] Change Mgmt subnet from `171.30.30.0/24` to `171.30.0.0/24` subnet.
- [x] Update static route for "VCF Mgmt Network" Next Hop Destination from `171.30.30.0/24` to `171.30.0.0/24`.
- [x] Move Mikrotik uplink ethernet5 to `USW-Lite-16-PoE` switch.
- [x] Update the switch profile for the port on the `USW-Lite-16-PoE` switch to be used for the uplink from the `MikroTik CRS304-4XG-IN` switch.
- [x] Setup Pihole Unbound for DNS.
- [ ] Recreate or migrate the Pihole/DNS VM to a different host
- [ ] Update DNS records in [DNS Policy Table](https://192.168.2.231/network/default/settings/policy-table?preset=dns-records).
- [ ] Install esxi-ms-a2-03 on 172.30.10.x.
- [ ] Speed test 10gbe ports
