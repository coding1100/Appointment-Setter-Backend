# PowerShell script to add SSH public key to VPS
# Usage: .\add_ssh_key_to_vps.ps1

$publicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICCptR4o+J8Bio17JdIUQ+6OOneiCLfNZk9/BzyIpwMQ github-actions"
$vpsHost = "root@148.230.93.34"

Write-Host "Adding SSH public key to VPS..." -ForegroundColor Green
Write-Host "VPS: $vpsHost" -ForegroundColor Yellow

# Create the command to add the key remotely
$command = @"
mkdir -p ~/.ssh && chmod 700 ~/.ssh && 
echo '$publicKey' >> ~/.ssh/authorized_keys && 
chmod 600 ~/.ssh/authorized_keys && 
echo 'SSH key added successfully!'
"@

# Execute the command
ssh -i C:\Users\MINDRIND\id_ed25519_appointment_setter $vpsHost $command

Write-Host "Done! Testing connection..." -ForegroundColor Green
ssh -i C:\Users\MINDRIND\id_ed25519_appointment_setter $vpsHost "echo 'Connection test successful!'"

