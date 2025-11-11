.PHONY: help setup sync install clean generate generate-all generate-host usb-create deploy-vcf-installer setup-vcf-installer fix-vsan-policy test lint format

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

fix-vsan-policy: sync ## Fix vSAN ESA storage policy for 2-node deployments
	@echo "$(GREEN)Fixing vSAN storage policy...$(NC)"
	@uv run scripts/fix_vsan_esa_default_storage_policy.py $(if $(CONFIG),--config $(CONFIG),)
	@echo "$(GREEN)✓ vSAN storage policy fixed$(NC)"

fix-vsan-policy-dryrun: sync ## Preview vSAN policy fix (dry run)
	@echo "$(YELLOW)Dry run: vSAN storage policy fix$(NC)"
	@uv run scripts/fix_vsan_esa_default_storage_policy.py --dry-run $(if $(CONFIG),--config $(CONFIG),)

##@ Development

test: sync ## Run tests (placeholder for future)
	@echo "$(YELLOW)No tests configured yet$(NC)"

lint: sync ## Lint Python code
	@echo "$(GREEN)Linting Python code...$(NC)"
	@uv run python -m py_compile scripts/generate_kickstart.py
	@uv run python -m py_compile scripts/create_esxi_usb.py
	@uv run python -m py_compile scripts/deploy_vcf_installer.py
	@uv run python -m py_compile scripts/setup_vcf_installer.py
	@uv run python -m py_compile scripts/fix_vsan_esa_default_storage_policy.py
	@echo "$(GREEN)✓ Linting complete$(NC)"

format: sync ## Format Python code (placeholder for future)
	@echo "$(YELLOW)No formatter configured yet$(NC)"

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
