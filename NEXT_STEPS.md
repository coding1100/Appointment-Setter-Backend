# 🚀 Next Steps After Setting Up GitHub Secrets

## ✅ Step 1: Add Public SSH Key to Your VPS

You need to add your **public key** (`id_ed25519_appointment_setter.pub`) to your VPS server.

### Option A: Using ssh-copy-id (Easiest)

```powershell
# From your local machine
ssh-copy-id -i C:\Users\MINDRIND\id_ed25519_appointment_setter.pub username@your-vps-host
```

### Option B: Manual Method

1. **Get your public key**:
   ```powershell
   cd C:\Users\MINDRIND
   Get-Content id_ed25519_appointment_setter.pub
   ```

2. **SSH into your VPS**:
   ```bash
   ssh username@your-vps-host
   ```

3. **Add the public key**:
   ```bash
   mkdir -p ~/.ssh
   chmod 700 ~/.ssh
   echo "ssh-ed25519 AAAA... github-actions" >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   ```

4. **Test the connection** (from your local machine):
   ```powershell
   ssh -i C:\Users\MINDRIND\id_ed25519_appointment_setter username@your-vps-host
   ```
   
   If it connects without password, you're good! ✅

---

## ✅ Step 2: Set Up VPS Server (If Not Done)

### Install Docker and Docker Compose

```bash
# SSH into your VPS
ssh username@your-vps-host

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version
```

### Set Up Project Directory

```bash
# Create deployment directory (use the path from VPS_DEPLOY_PATH secret)
sudo mkdir -p /opt/appointment-setter
cd /opt/appointment-setter

# Clone your repository
sudo git clone https://github.com/your-username/your-repo-name.git .

# Or if you already have the repo, just pull:
git pull origin main

# Make deploy script executable
chmod +x scripts/deploy.sh
```

### Set Up Environment Variables

```bash
# Copy environment example
cp env.example .env

# Edit .env with your production values
nano .env
# (Add all your production environment variables)
```

---

## ✅ Step 3: Commit and Push CI/CD Files

Now you need to commit all the CI/CD files we created:

```powershell
# Make sure you're in the project directory
cd C:\Users\MINDRIND\Desktop\Appointment-Setter-Backend

# Check what files were added
git status

# Add all new files
git add .github/
git add requirements-dev.txt
git add .flake8
git add pyproject.toml
git add scripts/

# Commit
git commit -m "Add CI/CD pipeline with GitHub Actions"

# Push to GitHub
git push origin main
```

**Note**: If your default branch is `master` instead of `main`, use:
```powershell
git push origin master
```

---

## ✅ Step 4: Test the Pipeline

### Test 1: Create a Pull Request (Recommended First)

1. **Create a test branch**:
   ```powershell
   git checkout -b test/ci-cd-pipeline
   ```

2. **Make a small change** (e.g., update README):
   ```powershell
   # Make any small change to test
   ```

3. **Commit and push**:
   ```powershell
   git add .
   git commit -m "Test CI/CD pipeline"
   git push origin test/ci-cd-pipeline
   ```

4. **Create Pull Request** on GitHub:
   - Go to your repository on GitHub
   - Click "Pull requests" → "New pull request"
   - Select your test branch → main
   - Create PR

5. **Check GitHub Actions**:
   - Go to "Actions" tab
   - You should see the workflow running
   - It will run: Lint → Security → Test
   - Build & Deploy won't run (only on main branch)

### Test 2: Push to Main (Full Pipeline)

Once PR tests pass, merge it to main:

1. **Merge the PR** on GitHub
2. **Check Actions tab**:
   - Should run all 5 jobs: Lint → Security → Test → Build → Deploy
3. **Check your VPS**:
   ```bash
   ssh username@your-vps-host
   cd /opt/appointment-setter
   docker-compose ps
   docker-compose logs -f
   ```

---

## 🔍 Step 5: Verify Everything Works

### Check GitHub Actions

1. Go to your repository → **Actions** tab
2. Click on the latest workflow run
3. Verify all jobs pass:
   - ✅ Lint and Format Check
   - ✅ Security Scan
   - ✅ Run Tests
   - ✅ Build and Push Docker Image (on main)
   - ✅ Deploy to VPS (on main)

### Check VPS Deployment

```bash
# SSH into VPS
ssh username@your-vps-host

# Check running containers
cd /opt/appointment-setter
docker-compose ps

# Check logs
docker-compose logs -f backend

# Test health endpoint
curl http://localhost:8001/health
```

---

## 🐛 Troubleshooting

### Pipeline Fails at Lint Stage

**Fix locally first**:
```powershell
# Install dev dependencies
pip install -r requirements-dev.txt

# Format code
black app/
isort app/

# Check linting
flake8 app/
```

### Pipeline Fails at Test Stage

- Check if tests pass locally: `pytest`
- Verify test environment variables are set correctly

### Deployment Fails

1. **Check SSH connection**:
   ```bash
   # Test from GitHub Actions context
   ssh -i ~/.ssh/key username@vps-host
   ```

2. **Check VPS logs**:
   ```bash
   ssh username@vps-host
   cd /opt/appointment-setter
   docker-compose logs
   ```

3. **Verify secrets are correct**:
   - Double-check all GitHub secrets
   - Verify VPS_DEPLOY_PATH matches actual path
   - Verify Docker Hub credentials

### Docker Build Fails

- Check Dockerfile syntax
- Verify all dependencies in requirements.txt
- Check Docker Hub credentials in secrets

---

## 📝 Quick Checklist

- [ ] Public SSH key added to VPS
- [ ] Docker and Docker Compose installed on VPS
- [ ] Project directory set up on VPS
- [ ] Environment variables configured on VPS
- [ ] CI/CD files committed and pushed to GitHub
- [ ] Test PR created and pipeline runs successfully
- [ ] Main branch deployment works
- [ ] VPS containers running correctly

---

## 🎉 You're Done!

Once all steps are complete, your CI/CD pipeline will:
- ✅ Automatically run tests on every PR
- ✅ Check code quality and security
- ✅ Build and push Docker images
- ✅ Deploy to VPS automatically on main branch

**Happy Deploying! 🚀**

