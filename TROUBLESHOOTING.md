# Troubleshooting Issues

## DNS Rate-Limiting Configuration Issue

### Problem Summary

**Root Cause:** Pi-hole was rate-limiting `192.168.10.250` (the NAT'd IP of my `sddcm01` VM)

**Why it happened:**

- VCF Installer validation makes ~15,000 DNS queries/minute
- Pi-hole's default rate limit: 1,000 queries/minute
- `192.168.10.250` exceeded the limit and got blocked
- All subsequent DNS queries returned **REFUSED**

**Solution:**

1. Restarted Pi-hole to clear the rate-limit block
2. Increased rate limit from 1,000 → 50,000 queries/minute
3. Removed conflicting `/etc/dnsmasq.d/02-vcf-lab.conf` file

The NAT issue (`172.30.0.21` → `192.168.10.250`) still exists but doesn't matter now since Pi-hole allows queries from that IP.
