#!/bin/bash

# Deployment script for VPS
# This script is executed on the VPS server after CI/CD pulls the latest code

set -e  # Exit on any error

echo "🚀 Starting deployment..."

# Configuration (can be overridden via environment variables)
DEPLOY_PATH=${VPS_DEPLOY_PATH:-/opt/appointment-setter}
DOCKER_IMAGE=${DOCKER_IMAGE:-umairmalick/appointment-setter-backend}
COMPOSE_FILE="docker-compose.yml"

cd "$DEPLOY_PATH" || exit 1

echo "📦 Pulling latest Docker image..."
docker pull "${DOCKER_IMAGE}:latest"

echo "🔄 Stopping existing containers..."
docker-compose -f "$COMPOSE_FILE" down

echo "🔧 Starting new containers..."
docker-compose -f "$COMPOSE_FILE" up -d

echo "🧹 Cleaning up old Docker images..."
docker image prune -f

echo "⏳ Waiting for services to be healthy..."
sleep 15

echo "✅ Verifying deployment..."
docker-compose -f "$COMPOSE_FILE" ps

# Check if containers are running
if docker-compose -f "$COMPOSE_FILE" ps | grep -q "Up"; then
    echo "✅ Deployment successful!"
    
    # Optional: Run health check
    if command -v curl &> /dev/null; then
        echo "🏥 Running health check..."
        sleep 5
        curl -f http://localhost:8001/health || echo "⚠️  Health check failed, but containers are running"
    fi
else
    echo "❌ Deployment failed - containers are not running"
    docker-compose -f "$COMPOSE_FILE" logs --tail=50
    exit 1
fi

echo "🎉 Deployment completed successfully!"

