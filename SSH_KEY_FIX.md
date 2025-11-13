# Fix SSH Key Authentication for Deployment

## Problem
GitHub Actions is failing with:
- `ssh.ParsePrivateKey: ssh: no key found`
- `ssh: handshake failed: ssh: unable to authenticate`

## Solution: Fix SSH Key Format in GitHub Secrets

The SSH private key in GitHub Secrets must be formatted correctly.

### Step 1: Get Your Private Key

On your local machine, run:
```powershell
cd C:\Users\MINDRIND
Get-Content id_ed25519_appointment_setter
```

**Important**: Copy the ENTIRE output including:
- `-----BEGIN OPENSSH PRIVATE KEY-----` (or `-----BEGIN PRIVATE KEY-----`)
- All the key content
- `-----END OPENSSH PRIVATE KEY-----` (or `-----END PRIVATE KEY-----`)

### Step 2: Update GitHub Secret

1. Go to: `https://github.com/coding1100/Appointment-Setter-Backend/settings/secrets/actions`
2. Find the secret: `VPS_SSH_KEY`
3. Click **Update** (or delete and recreate it)
4. Paste the ENTIRE private key content

### Step 3: Format Requirements

The key must:
- ✅ Include BEGIN and END markers
- ✅ Have newlines preserved (paste exactly as shown)
- ✅ Be the complete key (not just the middle part)
- ✅ Match exactly what's in your `id_ed25519_appointment_setter` file

### Example Format (DO NOT USE THIS - Use YOUR key):

```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACBzZXJ2ZXIta2V5LW5hbWUAAAAgVGhpcyBpcyBhIHByaXZhdGUga2V5IHNh
bXBsZSBkYXRhAAAAEAECAwQFBgcICQoLDA0ODwAAAQEBAQ==
-----END OPENSSH PRIVATE KEY-----
```

### Step 4: Verify Public Key is on VPS

Make sure your public key is in `~/.ssh/authorized_keys` on your VPS:

```bash
ssh -i C:\Users\MINDRIND\id_ed25519_appointment_setter root@148.230.93.34 "cat ~/.ssh/authorized_keys"
```

You should see your public key there. If not, add it:

```bash
# Get public key
cd C:\Users\MINDRIND
Get-Content id_ed25519_appointment_setter.pub

# Then on VPS, add it:
ssh root@148.230.93.34
cat >> ~/.ssh/authorized_keys
# Paste public key here, then press Ctrl+D
chmod 600 ~/.ssh/authorized_keys
exit
```

### Step 5: Test Locally

Before pushing, test SSH connection:
```powershell
ssh -i C:\Users\MINDRIND\id_ed25519_appointment_setter root@148.230.93.34 "echo 'SSH connection successful!'"
```

If this works, your key is correct. The GitHub secret should match exactly.

---

## Common Issues

### Issue 1: Missing BEGIN/END Markers
**Problem**: Only the key body was pasted, missing headers
**Solution**: Include the entire key including `-----BEGIN...-----` and `-----END...-----`

### Issue 2: Newlines Lost
**Problem**: Key was copied from a single-line format or had newlines removed
**Solution**: Copy the key exactly as it appears in the file, with all newlines preserved

### Issue 3: Extra Spaces/Characters
**Problem**: Extra whitespace or characters added during copy/paste
**Solution**: Copy directly from the file without editing

### Issue 4: Wrong Key Format
**Problem**: Using PPK format or other formats instead of OpenSSH
**Solution**: Make sure you're using the OpenSSH format private key

---

## Verification

After updating the secret, the next deployment should work. Check:
- The workflow should connect successfully
- No "no key found" errors
- Authentication should succeed

