.PHONY: help setup sync install clean generate generate-all generate-host usb-create list-vms delete-all-vms delete-all-vms-dryrun cleanup-vcf cleanup-vcf-dryrun deploy-vcf-installer setup-vcf-installer fix-vsan-policy fix-nsx-edge-amd fix-nsx-edge-amd-dryrun vcf-status vcf-validate vcf-capacity-audit vcf-cluster-capacity vcf-power-down vcf-power-down-dryrun vcf-power-up vcf-power-up-dryrun vcf-power-down-unused vcf-power-up-all test lint format format-imports check-imports

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m

##@ General

help: ## Display this help message
	@echo "$(GREEN)VCF 9.x in a Box - Makefile Commands$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "$(YELLOW)Usage:\n  $(BLUE)make$(NC) <target>\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  $(BLUE)%-27s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Security

check-secrets: sync ## Check secrets configuration and sources
	@uv run scripts/check_secrets.py

##@ Python Setup

setup: ## Install uv (if not already installed)
	@echo "$(GREEN)Checking for uv...$(NC)"
	@command -v uv >/dev/null 2>&1 || { \
		echo "$(YELLOW)uv not found. Installing...$(NC)"; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	}
	@echo "$(GREEN)✓ uv is installed$(NC)"

sync: setup ## Sync dependencies (creates .venv if needed)
	@echo "$(GREEN)Syncing dependencies...$(NC)"
	@uv sync
	@echo "$(GREEN)✓ Dependencies synced$(NC)"

install: sync ## Install project in development mode
	@echo "$(GREEN)Installing project...$(NC)"
	@uv pip install -e .
	@echo "$(GREEN)✓ Project installed$(NC)"

clean: ## Remove generated files and virtual environment
	@echo "$(YELLOW)Cleaning up...$(NC)"
	@rm -rf .venv/
	@rm -rf build/
	@rm -rf dist/
	@rm -rf *.egg-info/
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@echo "$(GREEN)✓ Cleaned$(NC)"

##@ Kickstart Generation

generate: sync ## Generate all ESXi kickstart configs (usage: make generate [CONFIG=path/to/config.yaml])
	@echo "$(GREEN)Generating all kickstart configs...$(NC)"
	@if [ -n "$(CONFIG)" ]; then \
		uv run scripts/generate_kickstart.py all --config $(CONFIG); \
	else \
		uv run scripts/generate_kickstart.py all; \
	fi
	@echo "$(GREEN)✓ All configs generated$(NC)"

generate-all: generate ## Alias for 'generate'

generate-host: sync ## Generate kickstart for specific host (usage: make generate-host HOST=1 [CONFIG=path/to/config.yaml])
	@if [ -z "$(HOST)" ]; then \
		echo "$(RED)ERROR: HOST not specified$(NC)"; \
		echo "Usage: make generate-host HOST=1 [CONFIG=path/to/config.yaml]"; \
		exit 1; \
	fi
	@echo "$(GREEN)Generating kickstart for host $(HOST)...$(NC)"
	@if [ -n "$(CONFIG)" ]; then \
		uv run scripts/generate_kickstart.py $(HOST) --config $(CONFIG); \
	else \
		uv run scripts/generate_kickstart.py $(HOST); \
	fi
	@echo "$(GREEN)✓ Config generated for host $(HOST)$(NC)"

generate-1: ## Generate kickstart for ESX01
	@$(MAKE) generate-host HOST=1

generate-2: ## Generate kickstart for ESX02
	@$(MAKE) generate-host HOST=2

generate-3: ## Generate kickstart for ESX03
	@$(MAKE) generate-host HOST=3

##@ USB Creation

usb-create: ## Create bootable USB (usage: make usb-create USB=/dev/disk4 HOST=1)
	@if [ -z "$(USB)" ] || [ -z "$(HOST)" ]; then \
		echo "$(RED)ERROR: USB or HOST not specified$(NC)"; \
		echo "Usage: make usb-create USB=/dev/disk4 HOST=1"; \
		echo ""; \
		echo "To find your USB device, run: diskutil list"; \
		exit 1; \
	fi
	@echo "$(YELLOW)Creating bootable USB for ESX0$(HOST)...$(NC)"
	@sudo uv run scripts/create_esxi_usb.py $(USB) $(HOST) $(if $(CONFIG),--config $(CONFIG),)

usb-list: ## List available disk devices
	@uv run scripts/create_esxi_usb.py --list

refind-usb-create: ## Create rEFInd multi-host boot menu USB
	@if [ -z "$(USB)" ]; then \
		echo "$(RED)ERROR: USB not specified$(NC)"; \
		echo "Usage: make refind-usb-create USB=/dev/disk4"; \
		echo ""; \
		echo "Creates a single USB with rEFInd boot menu for all hosts"; \
		exit 1; \
	fi
	@echo "$(YELLOW)Creating rEFInd boot menu USB...$(NC)"
	@sudo uv run scripts/create_refind_usb.py $(USB) $(if $(CONFIG),--config $(CONFIG),) $(if $(LABEL),--label $(LABEL),)

refind-usb-dryrun: ## Preview rEFInd USB creation (dry run)
	@if [ -z "$(USB)" ]; then \
		echo "$(RED)ERROR: USB not specified$(NC)"; \
		echo "Usage: make refind-usb-dryrun USB=/dev/disk4"; \
		exit 1; \
	fi
	@echo "$(YELLOW)Dry run: rEFInd USB creation$(NC)"
	@uv run scripts/create_refind_usb.py --dry-run $(USB) $(if $(CONFIG),--config $(CONFIG),)

##@ ESXi Configuration

setup-ssh-keys: sync ## Setup SSH keys for ESXi hosts (password-less SSH)
	@echo "$(GREEN)Setting up SSH keys for ESXi hosts...$(NC)"
	@uv run scripts/setup_esxi_ssh_keys.py $(if $(CONFIG),--config $(CONFIG),) $(if $(KEY),--key-name $(KEY),)
	@echo "$(GREEN)✓ SSH keys configured$(NC)"

setup-ssh-keys-dryrun: sync ## Preview SSH key setup (dry run)
	@echo "$(YELLOW)Dry run: SSH key setup$(NC)"
	@uv run scripts/setup_esxi_ssh_keys.py --dry-run $(if $(CONFIG),--config $(CONFIG),) $(if $(KEY),--key-name $(KEY),)

##@ VCF Deployment

list-vms: sync ## List all VMs on all ESXi hosts
	@echo "$(GREEN)Listing VMs on all hosts...$(NC)"
	@uv run scripts/list_vms.py $(if $(CONFIG),--config $(CONFIG),)

delete-all-vms: sync ## Delete all VMs from all ESXi hosts (use EXCLUDE to skip VMs)
	@echo "$(RED)Deleting all VMs...$(NC)"
	@uv run scripts/delete_all_vms.py $(if $(EXCLUDE),--exclude $(EXCLUDE),) $(if $(CONFIG),--config $(CONFIG),)

delete-all-vms-dryrun: sync ## Preview VM deletion (dry run)
	@echo "$(YELLOW)Dry run: Delete all VMs$(NC)"
	@uv run scripts/delete_all_vms.py --dry-run $(if $(EXCLUDE),--exclude $(EXCLUDE),) $(if $(CONFIG),--config $(CONFIG),)

cleanup-vcf: sync ## Clean up failed VCF deployment (remove Installer VM & reset hosts)
	@echo "$(YELLOW)Cleaning up VCF deployment...$(NC)"
	@uv run scripts/cleanup_vcf_deployment.py $(if $(CONFIG),--config $(CONFIG),)

cleanup-vcf-dryrun: sync ## Preview VCF cleanup (dry run)
	@echo "$(YELLOW)Dry run: VCF cleanup$(NC)"
	@uv run scripts/cleanup_vcf_deployment.py --dry-run $(if $(CONFIG),--config $(CONFIG),)

deploy-vcf-installer: sync ## Deploy VCF Installer OVA to ESXi host
	@echo "$(GREEN)Deploying VCF Installer...$(NC)"
	@uv run scripts/deploy_vcf_installer.py $(if $(CONFIG),--config $(CONFIG),)
	@echo "$(GREEN)✓ VCF Installer deployed$(NC)"

deploy-vcf-installer-dryrun: sync ## Preview VCF Installer deployment (dry run)
	@echo "$(YELLOW)Dry run: VCF Installer deployment$(NC)"
	@uv run scripts/deploy_vcf_installer.py --dry-run $(if $(CONFIG),--config $(CONFIG),)

setup-vcf-installer: sync ## Configure VCF Installer post-deployment
	@echo "$(GREEN)Configuring VCF Installer...$(NC)"
	@uv run scripts/setup_vcf_installer.py $(if $(CONFIG),--config $(CONFIG),)
	@echo "$(GREEN)✓ VCF Installer configured$(NC)"

setup-vcf-installer-dryrun: sync ## Preview VCF Installer configuration (dry run)
	@echo "$(YELLOW)Dry run: VCF Installer configuration$(NC)"
	@uv run scripts/setup_vcf_installer.py --dry-run $(if $(CONFIG),--config $(CONFIG),)

validate-vcf-installer: sync ## Validate VCF Installer configuration was applied
	@echo "$(GREEN)Validating VCF Installer configuration...$(NC)"
	@uv run scripts/validate_vcf_installer_config.py $(if $(CONFIG),--config $(CONFIG),)

# fix-vsan-policy: sync ## Fix vSAN ESA storage policy for 2-node deployments
# 	@echo "$(GREEN)Fixing vSAN storage policy...$(NC)"
# 	@uv run scripts/fix_vsan_esa_default_storage_policy.py $(if $(CONFIG),--config $(CONFIG),)
# 	@echo "$(GREEN)✓ vSAN storage policy fixed$(NC)"

# fix-vsan-policy-dryrun: sync ## Preview vSAN policy fix (dry run)
# 	@echo "$(YELLOW)Dry run: vSAN storage policy fix$(NC)"
# 	@uv run scripts/fix_vsan_esa_default_storage_policy.py --dry-run $(if $(CONFIG),--config $(CONFIG),)

# fix-vsan-hcl-timestamp: sync ## Fix vSAN HCL timestamp for VCF 9.0.1
# 	@echo "$(GREEN)Fixing vSAN HCL timestamp...$(NC)"
# 	@uv run scripts/fix_vsan_hcl_timestamp.py $(if $(CONFIG),--config $(CONFIG),)
# 	@echo "$(GREEN)✓ vSAN HCL timestamp fixed$(NC)"

# fix-vsan-hcl-timestamp-dryrun: sync ## Preview vSAN HCL timestamp fix (dry run)
# 	@echo "$(YELLOW)Dry run: vSAN HCL timestamp fix$(NC)"
# 	@uv run scripts/fix_vsan_hcl_timestamp.py --dry-run $(if $(CONFIG),--config $(CONFIG),)

fix-vsan-hcl-bypass: sync ## Enable vSAN ESA HCL bypass (VCF 9.0.1 built-in)
	@echo "$(GREEN)Enabling vSAN ESA HCL bypass...$(NC)"
	@uv run scripts/fix_vsan_hcl_bypass.py $(if $(CONFIG),--config $(CONFIG),)
	@echo "$(GREEN)✓ vSAN ESA HCL bypass enabled$(NC)"

fix-vsan-hcl-bypass-dryrun: sync ## Preview vSAN ESA HCL bypass (dry run)
	@echo "$(YELLOW)Dry run: vSAN ESA HCL bypass$(NC)"
	@uv run scripts/fix_vsan_hcl_bypass.py --dry-run $(if $(CONFIG),--config $(CONFIG),)

##@ NSX Edge (AMD Ryzen)

fix-nsx-edge-amd: sync ## Fix NSX Edge for AMD Ryzen CPUs (usage: make fix-nsx-edge-amd PASSWORD='EdgePass')
	@if [ -z "$(PASSWORD)" ]; then \
		echo "$(RED)ERROR: PASSWORD not specified$(NC)"; \
		echo "Usage: make fix-nsx-edge-amd PASSWORD='YourEdgePassword'"; \
		echo ""; \
		echo "Get the password from your VCF manifest JSON:"; \
		echo "  nsxTSpec.nsxEdgeSpec.nsxEdgeAdminPassword"; \
		exit 1; \
	fi
	@echo "$(GREEN)Applying NSX Edge AMD Ryzen fix...$(NC)"
	@uv run scripts/fix_nsx_edge_amd_ryzen.py --password '$(PASSWORD)' $(if $(EDGES),--edges $(EDGES),) $(if $(CONFIG),--config $(CONFIG),)
	@echo "$(GREEN)✓ NSX Edge AMD fix applied$(NC)"

fix-nsx-edge-amd-dryrun: sync ## Preview NSX Edge AMD fix (dry run)
	@if [ -z "$(PASSWORD)" ]; then \
		echo "$(RED)ERROR: PASSWORD not specified$(NC)"; \
		echo "Usage: make fix-nsx-edge-amd-dryrun PASSWORD='YourEdgePassword'"; \
		exit 1; \
	fi
	@echo "$(YELLOW)Dry run: NSX Edge AMD Ryzen fix$(NC)"
	@uv run scripts/fix_nsx_edge_amd_ryzen.py --dry-run --password '$(PASSWORD)' $(if $(EDGES),--edges $(EDGES),) $(if $(CONFIG),--config $(CONFIG),)

##@ VCF Management Capacity

vcf-status: sync ## Show power state of all VCF management VMs
	@echo "$(GREEN)Checking VCF management VM status...$(NC)"
	@uv run scripts/vcf_management_power.py status $(if $(TIER),$(TIER),)

vcf-validate: sync ## Validate environment before power operations
	@echo "$(GREEN)Validating VCF environment...$(NC)"
	@uv run scripts/vcf_management_power.py validate

vcf-capacity-audit: sync ## Audit capacity usage of management VMs
	@echo "$(GREEN)Running capacity audit...$(NC)"
	@uv run scripts/vcf_capacity_audit.py $(if $(VM),--vm-name $(VM),) $(if $(CSV),--export-csv $(CSV),)

vcf-cluster-capacity: sync ## Quick cluster capacity overview
	@echo "$(GREEN)Checking cluster capacity...$(NC)"
	@uv run scripts/vcf_capacity_audit.py --cluster-summary-only

vcf-power-down: sync ## Power down management VMs (usage: make vcf-power-down TIER=tier3)
	@if [ -z "$(TIER)" ]; then \
		echo "$(RED)ERROR: TIER not specified$(NC)"; \
		echo "Usage: make vcf-power-down TIER=tier3"; \
		echo ""; \
		echo "Available tiers:"; \
		echo "  tier2 - Management-only components (VCF Operations Console, vROps)"; \
		echo "  tier3 - Optional features (Automation, Identity Broker, etc.)"; \
		echo "  all   - All management VMs (tier2 + tier3)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)Powering down $(TIER) VMs...$(NC)"
	@uv run scripts/vcf_management_power.py power-down $(TIER)

vcf-power-down-dryrun: sync ## Preview power down operation (dry run)
	@if [ -z "$(TIER)" ]; then \
		echo "$(RED)ERROR: TIER not specified$(NC)"; \
		echo "Usage: make vcf-power-down-dryrun TIER=tier3"; \
		exit 1; \
	fi
	@echo "$(YELLOW)Dry run: Power down $(TIER) VMs$(NC)"
	@uv run scripts/vcf_management_power.py --dry-run power-down $(TIER)

vcf-power-up: sync ## Power up management VMs (usage: make vcf-power-up TIER=tier3)
	@if [ -z "$(TIER)" ]; then \
		echo "$(RED)ERROR: TIER not specified$(NC)"; \
		echo "Usage: make vcf-power-up TIER=tier3"; \
		echo ""; \
		echo "Available tiers:"; \
		echo "  tier2 - Management-only components"; \
		echo "  tier3 - Optional features"; \
		echo "  all   - All management VMs"; \
		exit 1; \
	fi
	@echo "$(GREEN)Powering up $(TIER) VMs...$(NC)"
	@uv run scripts/vcf_management_power.py power-up $(TIER)

vcf-power-up-dryrun: sync ## Preview power up operation (dry run)
	@if [ -z "$(TIER)" ]; then \
		echo "$(RED)ERROR: TIER not specified$(NC)"; \
		echo "Usage: make vcf-power-up-dryrun TIER=tier3"; \
		exit 1; \
	fi
	@echo "$(YELLOW)Dry run: Power up $(TIER) VMs$(NC)"
	@uv run scripts/vcf_management_power.py --dry-run power-up $(TIER)

vcf-power-down-unused: sync ## Quick command: Power down all unused management VMs (tier3)
	@echo "$(YELLOW)Powering down unused management VMs (Tier 3)...$(NC)"
	@uv run scripts/vcf_management_power.py power-down tier3

vcf-power-up-all: sync ## Quick command: Power up all management VMs
	@echo "$(GREEN)Powering up all management VMs...$(NC)"
	@uv run scripts/vcf_management_power.py power-up all

##@ Development

test: sync ## Run tests (placeholder for future)
	@echo "$(YELLOW)No tests configured yet$(NC)"

lint: sync ## Lint Python code with ruff
	@echo "$(GREEN)Linting Python code...$(NC)"
	@uv run ruff check scripts/
	@echo "$(GREEN)✓ Linting complete$(NC)"

format: sync ## Format Python code with ruff
	@echo "$(GREEN)Formatting Python code...$(NC)"
	@uv run ruff format scripts/
	@echo "$(GREEN)✓ Formatting complete$(NC)"

format-imports: sync ## Organize imports and remove unused ones
	@echo "$(GREEN)Organizing imports and removing unused...$(NC)"
	@uv run ruff check --select I,F401 --fix scripts/
	@echo "$(GREEN)✓ Imports organized$(NC)"

check-imports: sync ## Check imports without modifying
	@echo "$(GREEN)Checking imports...$(NC)"
	@uv run ruff check --select I,F401 scripts/

##@ Quick Reference

info: ## Show project information
	@echo "$(GREEN)Project Information$(NC)"
	@echo "  Name:        vcf-9x-in-box"
	@echo "  Python:      $$(python3 --version 2>/dev/null || echo 'Not found')"
	@echo "  uv:          $$(uv --version 2>/dev/null || echo 'Not installed')"
	@echo "  VirtualEnv:  $$([ -d .venv ] && echo 'Exists' || echo 'Not created')"
	@echo ""
	@echo "$(GREEN)Host Configuration$(NC)"
	@echo "  ESX01:       172.30.0.11 (esx01.vcf.lab)"
	@echo "  ESX02:       172.30.0.12 (esx02.vcf.lab)"
	@echo "  ESX03:       172.30.0.13 (esx03.vcf.lab)"
	@echo "  VCF:         172.30.0.21 (sddcm01.vcf.lab)"
	@echo ""
	@echo "$(GREEN)Network Configuration$(NC)"
	@echo "  Network:     172.30.0.0/24"
	@echo "  Gateway:     172.30.0.1"
	@echo "  VLAN:        30"
	@echo "  DNS:         192.168.10.2"

all: clean sync generate ## Clean, sync, and generate all configs
	@echo "$(GREEN)✓ All tasks complete$(NC)"
