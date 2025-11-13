# SSH Key Setup Guide for CI/CD

## ✅ Step 1: You've Generated the SSH Key Pair

Great! You've created:
- **Private key**: `id_ed25519_appointment_setter` (keep this SECRET!)
- **Public key**: `id_ed25519_appointment_setter.pub` (safe to share)

## 🔐 Step 2: Add Private Key to GitHub Secrets

1. **Display your private key** (in PowerShell):
   ```powershell
   cd C:\Users\MINDRIND
   Get-Content id_ed25519_appointment_setter
   ```

2. **Copy the entire output** (includes `-----BEGIN OPENSSH PRIVATE KEY-----` to `-----END OPENSSH PRIVATE KEY-----`)

3. **Add to GitHub Secrets**:
   - Go to your GitHub repository
   - Click **Settings** → **Secrets and variables** → **Actions**
   - Click **New repository secret**
   - Name: `VPS_SSH_KEY`
   - Value: Paste the entire private key content
   - Click **Add secret**

## 🔓 Step 3: Add Public Key to Your VPS Server

1. **Display your public key** (in PowerShell):
   ```powershell
   cd C:\Users\MINDRIND
   Get-Content id_ed25519_appointment_setter.pub
   ```

2. **Copy the public key** (looks like: `ssh-ed25519 AAAA... github-actions`)

3. **Add to your VPS**:
   ```bash
   # SSH into your VPS
   ssh username@your-vps-host
   
   # Create .ssh directory if it doesn't exist
   mkdir -p ~/.ssh
   chmod 700 ~/.ssh
   
   # Add public key to authorized_keys
   echo "ssh-ed25519 AAAA... github-actions" >> ~/.ssh/authorized_keys
   
   # Set correct permissions
   chmod 600 ~/.ssh/authorized_keys
   ```

   Or use `ssh-copy-id` if available:
   ```bash
   ssh-copy-id -i id_ed25519_appointment_setter.pub username@your-vps-host
   ```

## ✅ Step 4: Test SSH Connection

From your local machine, test the connection:
```powershell
ssh -i C:\Users\MINDRIND\id_ed25519_appointment_setter username@your-vps-host
```

If it connects without asking for a password, you're all set! ✅

## 🔒 Security Notes

- ⚠️ **NEVER** commit the private key (`id_ed25519_appointment_setter`) to Git
- ⚠️ **NEVER** share the private key publicly
- ✅ The private key should only be stored in GitHub Secrets
- ✅ The public key is safe to share and add to your VPS

## 🐛 Troubleshooting

### SSH Connection Fails
1. Verify public key was added correctly:
   ```bash
   cat ~/.ssh/authorized_keys
   ```

2. Check SSH permissions on VPS:
   ```bash
   chmod 700 ~/.ssh
   chmod 600 ~/.ssh/authorized_keys
   ```

3. Check SSH service status:
   ```bash
   sudo systemctl status ssh
   ```

### GitHub Actions Can't Connect
1. Verify `VPS_SSH_KEY` secret is set correctly in GitHub
2. Verify `VPS_HOST` and `VPS_USERNAME` are correct
3. Check GitHub Actions logs for detailed error messages

