# CI/CD Pipeline Setup Guide

This guide will help you set up the CI/CD pipeline for the Appointment Setter Backend project.

## 📋 Prerequisites

1. **GitHub Repository**: Your code must be in a GitHub repository
2. **Docker Hub Account**: For pushing Docker images
3. **VPS Server**: With Docker and Docker Compose installed
4. **SSH Access**: To your VPS server

## 🔐 Step 1: Configure GitHub Secrets

Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add the following secrets:

### Docker Hub Credentials
- `DOCKER_USERNAME`: Your Docker Hub username (e.g., `umairmalick`)
- `DOCKER_PASSWORD`: Your Docker Hub password or access token

### VPS Deployment Credentials
- `VPS_HOST`: Your VPS server IP or domain (e.g., `123.45.67.89` or `server.example.com`)
- `VPS_USERNAME`: SSH username for VPS (e.g., `root` or `ubuntu`)
- `VPS_SSH_KEY`: Private SSH key for VPS access
  ```bash
  # Generate SSH key if you don't have one:
  ssh-keygen -t ed25519 -C "github-actions"
  
  # Copy the private key content:
  cat ~/.ssh/id_ed25519
  
  # Add public key to VPS:
  ssh-copy-id -i ~/.ssh/id_ed25519.pub username@your-vps-host
  ```
- `VPS_PORT`: SSH port (optional, default: 22)
- `VPS_DEPLOY_PATH`: Path where your project is deployed (e.g., `/opt/appointment-setter`)

## 🐳 Step 2: Set Up VPS Server

### Install Docker and Docker Compose

```bash
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
# Create deployment directory
sudo mkdir -p /opt/appointment-setter
cd /opt/appointment-setter

# Clone your repository
sudo git clone https://github.com/your-username/your-repo.git .

# Make deploy script executable
chmod +x scripts/deploy.sh
```

### Set Up Environment Variables

```bash
# Copy environment example
cp env.example .env

# Edit .env with your production values
nano .env
```

## 🔄 Step 3: Initial Deployment

### Manual Initial Setup

On your VPS:

```bash
cd /opt/appointment-setter

# Log in to Docker Hub
docker login

# Pull and start services
docker-compose up -d

# Verify deployment
docker-compose ps
docker-compose logs -f
```

## 🚀 Step 4: Test the CI/CD Pipeline

### Test on Pull Request

1. Create a new branch:
   ```bash
   git checkout -b feature/test-ci-cd
   ```

2. Make a small change and commit:
   ```bash
   git add .
   git commit -m "Test CI/CD pipeline"
   git push origin feature/test-ci-cd
   ```

3. Create a Pull Request to `main` or `develop` branch

4. Check GitHub Actions tab to see:
   - ✅ Linting checks
   - ✅ Security scans
   - ✅ Tests running

### Test Deployment on Main Branch

1. Merge your PR to `main` branch

2. GitHub Actions will automatically:
   - Run all checks
   - Build Docker image
   - Push to Docker Hub
   - Deploy to VPS

3. Monitor the deployment:
   - Go to **Actions** tab in GitHub
   - Watch the workflow progress
   - Check VPS logs: `docker-compose logs -f`

## 📊 Pipeline Stages

The CI/CD pipeline consists of 5 stages:

### 1. **Lint** (Runs on every push/PR)
- Code formatting check (Black)
- Import sorting check (isort)
- Linting (Flake8)

### 2. **Security** (Runs on every push/PR)
- Security linting (Bandit)
- Dependency vulnerability check (Safety)

### 3. **Test** (Runs on every push/PR)
- Unit and integration tests
- Coverage reports
- Uses Redis service for testing

### 4. **Build & Push** (Runs on push to main/develop)
- Builds Docker image
- Pushes to Docker Hub
- Creates tags (latest, branch-name, commit-sha)

### 5. **Deploy** (Runs on push to main only)
- SSH into VPS
- Pulls latest code
- Pulls latest Docker image
- Restarts services
- Cleans up old images

## 🔧 Customization

### Change Docker Image Name

Edit `.github/workflows/ci-cd.yml`:
```yaml
env:
  DOCKER_IMAGE: your-username/your-image-name
```

### Change Branch Names

Edit `.github/workflows/ci-cd.yml`:
```yaml
on:
  push:
    branches: [ main, develop, production ]  # Add your branches
```

### Skip Deployment for Certain Commits

Add `[skip ci]` or `[ci skip]` to your commit message:
```bash
git commit -m "Update README [skip ci]"
```

## 🐛 Troubleshooting

### Pipeline Fails at Lint Stage

```bash
# Run locally to fix:
black app/
isort app/
flake8 app/
```

### Docker Build Fails

Check Dockerfile and ensure all dependencies are correct:
```bash
docker build -t test-image .
```

### Deployment Fails

1. Check SSH connection:
   ```bash
   ssh -i ~/.ssh/your-key username@your-vps-host
   ```

2. Verify Docker is running on VPS:
   ```bash
   ssh username@vps "docker ps"
   ```

3. Check GitHub Actions logs for detailed error messages

### VPS Can't Pull Docker Image

1. Ensure Docker Hub credentials are correct in secrets
2. Check if image was pushed successfully
3. Verify network connectivity on VPS

## 📝 Notes

- The pipeline runs tests against a Redis service (automatically provided by GitHub Actions)
- Production environment variables are NOT used during testing
- Docker images are cached to speed up builds
- Old Docker images are automatically cleaned up after deployment

## 🔒 Security Best Practices

1. **Never commit secrets**: All sensitive data should be in GitHub Secrets
2. **Use SSH keys**: Prefer SSH keys over passwords for VPS access
3. **Rotate credentials**: Regularly update Docker Hub and SSH credentials
4. **Review dependencies**: Regularly run `safety check` to find vulnerable packages
5. **Monitor logs**: Check deployment logs regularly for any issues

## 📞 Support

If you encounter any issues:
1. Check GitHub Actions logs
2. Review this documentation
3. Check VPS server logs: `docker-compose logs -f`
4. Verify all secrets are correctly configured

---

**Happy Deploying! 🚀**

