# ------------------------ Config ------------------------
$vcFqdn = "vc01.vcf.lab"
$vcUsername = "administrator@vsphere.local"
$vcPassword = ConvertTo-SecureString "VMware1!VMware1!" -AsPlainText -Force
$vcCreds = New-Object System.Management.Automation.PSCredential ($vcUsername, $vcPassword)

$pingInterval = 900      # 15 minutes in seconds
$connectInterval = 600   # 10 minutes in seconds
$policyCheckInterval = 60 # 1 minutes in seconds

# Your final snippet to run when everything is ready
$finalAction = {
    Write-Output "✅ Running post-deployment task..."
    # PLACE YOUR SNIPPET HERE (example below)
    Get-VM | Select Name, PowerState
}

# --------------------- Begin Logic ----------------------

function Wait-ForPing {
    while (-not (Test-Connection -ComputerName $vcFqdn -Count 1 -Quiet)) {
        Write-Output "⏳ vCenter not pingable yet. Sleeping for $($pingInterval / 60) minutes..."
        Start-Sleep -Seconds $pingInterval
    }
    Write-Output "✅ vCenter is pingable!"
}

function Wait-ForVCenterConnection {
    while ($true) {
        try {
            Connect-VIServer -Server $vcFqdn -Credential $vcCreds -ErrorAction Stop | Out-Null
            Write-Output "✅ Connected to vCenter!"
            break
        } catch {
            Write-Output "⏳ vCenter is not ready for login yet. Sleeping for $($connectInterval / 60) minutes..."
            Start-Sleep -Seconds $connectInterval
        }
    }
}

function Wait-ForVCFPolicy {
    while ($true) {
        try {
            $vcfStoragePolicy = Get-SpbmStoragePolicy -ErrorAction Stop | Where-Object { $_.Name -match "VCF" }
            if ($vcfStoragePolicy) {
                Write-Output "✅ VCF Storage Policy is now available!"
                break
            } else {
                Write-Output "⏳ VCF Storage Policy not found. Sleeping for $($policyCheckInterval / 60) minutes..."
                Start-Sleep -Seconds $policyCheckInterval
            }
        } catch {
            Write-Output "⏳ Storage Policy service not ready yet. Sleeping for $($policyCheckInterval / 60) minutes..."
            Start-Sleep -Seconds $policyCheckInterval
        }
    }
}

# ------------------------ Run Steps ------------------------
Write-Output "🔍 Checking if vCenter ($vcFqdn) is ready..."
Wait-ForPing
Wait-ForVCenterConnection
Wait-ForVCFPolicy

# Non-AI Generated Code ;)
Write-Output "✅ Updating VCF Storage Policy"
$vcfStoragePolicy = Get-SpbmStoragePolicy | where {$_.Name -match "VCF"}
$rule = New-SpbmRule -Capability (Get-SpbmCapability -Name 'VSAN.hostFailuresToTolerate') -Value 0
$ruleSet = New-SpbmRuleSet -AllOfRules $rule
Set-SpbmStoragePolicy -StoragePolicy $vcfStoragePolicy -AnyOfRuleSets $ruleSet | Out-Null

# Disconnect
Disconnect-VIServer * -Confirm:$false
Write-Output "✅ Disconnected from vCenter"
