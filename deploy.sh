#!/bin/bash
# ORB Strategy Deployment Script

echo "Deploying ORB Stock Trading Strategy..."

# Optional: Build dashboard locally before Docker build (for development)
# cd dashboard && npm install && npm run build && cd ..

# Build and start services (dashboard will be built during docker build)
docker-compose build
docker-compose up -d

# Show status
docker-compose ps

echo "ORB Strategy deployed successfully!"
echo "Use 'docker-compose logs -f orb-stocks' to view logs"