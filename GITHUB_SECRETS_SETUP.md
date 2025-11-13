# GitHub Secrets Setup Guide

## Required GitHub Secrets for CI/CD

You need to add these secrets to your GitHub repository for the CI/CD pipeline to work.

### How to Add Secrets

1. Go to your GitHub repository: `https://github.com/coding1100/Appointment-Setter-Backend`
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each secret below

---

## Required Secrets (for Tests & Deployment)

### 1. Docker Hub Credentials
- **Name**: `DOCKER_USERNAME`
- **Value**: Your Docker Hub username (e.g., `umairmalick`)

- **Name**: `DOCKER_PASSWORD`
- **Value**: Your Docker Hub password or access token

---

### 2. Firebase Configuration
These should match your VPS `.env` file:

- **Name**: `FIREBASE_PROJECT_ID`
- **Value**: Your Firebase project ID

- **Name**: `FIREBASE_PRIVATE_KEY`
- **Value**: Your Firebase private key (the entire key including `-----BEGIN PRIVATE KEY-----` and `-----END PRIVATE KEY-----`)

- **Name**: `FIREBASE_CLIENT_EMAIL`
- **Value**: Your Firebase service account email (e.g., `your-service-account@project.iam.gserviceaccount.com`)

---

### 3. Security
- **Name**: `SECRET_KEY`
- **Value**: Your secret key (min 32 characters) - same as on VPS

---

### 4. LiveKit Configuration
- **Name**: `LIVEKIT_API_KEY`
- **Value**: Your LiveKit API key

- **Name**: `LIVEKIT_API_SECRET`
- **Value**: Your LiveKit API secret

- **Name**: `LIVEKIT_URL`
- **Value**: Your LiveKit WebSocket URL (e.g., `wss://your-livekit-server.livekit.cloud`)

---

### 5. VPS Deployment Credentials
- **Name**: `VPS_HOST`
- **Value**: Your VPS IP or domain (e.g., `148.230.93.34`)

- **Name**: `VPS_USERNAME`
- **Value**: SSH username (e.g., `root`)

- **Name**: `VPS_SSH_KEY`
- **Value**: Your private SSH key content (from `id_ed25519_appointment_setter`)

- **Name**: `VPS_PORT` (optional)
- **Value**: SSH port (default: `22`)

- **Name**: `VPS_DEPLOY_PATH` (optional)
- **Value**: Deployment path (e.g., `/root/appointment-setter`)

---

## Optional Secrets (for Tests)

These are optional but recommended if your tests use them:

- **Name**: `GOOGLE_API_KEY`
- **Value**: Your Google AI (Gemini) API key

- **Name**: `DEEPGRAM_API_KEY`
- **Value**: Your Deepgram API key

- **Name**: `ELEVEN_API_KEY`
- **Value**: Your ElevenLabs API key

- **Name**: `SENDGRID_API_KEY`
- **Value**: Your SendGrid API key

- **Name**: `SENDGRID_FROM_EMAIL`
- **Value**: Your SendGrid from email address

---

## Quick Copy from VPS

If you have SSH access to your VPS, you can view your `.env` file:

```bash
ssh root@148.230.93.34
cat /root/appointment-setter/.env
```

Then copy the values and paste them into GitHub Secrets.

---

## Security Notes

- ⚠️ **Never** commit these values to your repository
- ✅ Always use GitHub Secrets for sensitive data
- ✅ These secrets are encrypted and only accessible during workflow runs
- ✅ Only repository admins can view/edit secrets

---

## Verification

After adding all secrets, the CI/CD pipeline should:
1. ✅ Pass all linting checks
2. ✅ Pass security scans
3. ✅ Run tests successfully
4. ✅ Build and push Docker images
5. ✅ Deploy to VPS automatically

Check your workflow runs at: `https://github.com/coding1100/Appointment-Setter-Backend/actions`

