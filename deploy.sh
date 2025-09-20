#!/bin/bash
# ORB Strategy Deployment Script

echo "Deploying ORB Stock Trading Strategy..."

# Build and start services
docker-compose build
docker-compose up -d

# Show status
docker-compose ps

echo "ORB Strategy deployed successfully!"
echo "Use 'docker-compose logs -f orb-stocks' to view logs"