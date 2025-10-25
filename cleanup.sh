#!/bin/bash

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}================================${NC}"
echo -e "${YELLOW}  Docker Ecosystem Cleanup Tool${NC}"
echo -e "${YELLOW}================================${NC}"
echo ""

# Check if docker-compose.yml exists
if [ ! -f "docker-compose.yml" ] && [ ! -f "docker-compose.yaml" ] && [ ! -f "compose.yml" ] && [ ! -f "compose.yaml" ]; then
    echo -e "${RED}ERROR: No docker-compose file found in current directory!${NC}"
    echo -e "${YELLOW}Please run this script from a directory containing a docker-compose file.${NC}"
    exit 1
fi

# Confirmation prompt
echo -e "${RED}WARNING: This will remove ALL containers, volumes, and data for this Docker Compose project!${NC}"
echo -e "${RED}This action cannot be undone.${NC}"
echo ""
echo -e "${YELLOW}Current directory: $(pwd)${NC}"
echo ""
read -p "Are you sure you want to continue? (yes/no): " -r
echo ""

if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo -e "${GREEN}Cleanup cancelled.${NC}"
    exit 0
fi

echo -e "${YELLOW}Starting cleanup process...${NC}"
echo ""

# Step 1: Stop and remove all containers with volumes
echo -e "${GREEN}[1/4] Stopping containers and removing volumes...${NC}"
docker-compose down -v --remove-orphans
echo -e "${GREEN}✓ Containers stopped and volumes removed${NC}"
echo ""

# Step 2: Remove any remaining project volumes
echo -e "${GREEN}[2/4] Removing any remaining project volumes...${NC}"
project_name=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]//g')
remaining_volumes=$(docker volume ls --filter "name=${project_name}" -q)
if [ -n "$remaining_volumes" ]; then
    echo "$remaining_volumes" | xargs docker volume rm 2>/dev/null || echo -e "${YELLOW}  Some volumes may be in use${NC}"
    echo -e "${GREEN}✓ Remaining volumes removed${NC}"
else
    echo -e "${YELLOW}No remaining volumes found${NC}"
fi
echo ""

# Step 3: Remove project networks
echo -e "${GREEN}[3/4] Removing project networks...${NC}"
remaining_networks=$(docker network ls --filter "name=${project_name}" -q)
if [ -n "$remaining_networks" ]; then
    echo "$remaining_networks" | xargs docker network rm 2>/dev/null || echo -e "${YELLOW}  Some networks may be in use${NC}"
    echo -e "${GREEN}✓ Networks removed${NC}"
else
    echo -e "${YELLOW}No remaining networks found${NC}"
fi
echo ""

# Step 4: Optional - Clean up dangling resources
echo -e "${GREEN}[4/4] Cleaning up dangling Docker resources...${NC}"
read -p "Do you want to remove dangling images and volumes? (yes/no): " -r
echo ""
if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    docker system prune -f --volumes
    echo -e "${GREEN}✓ Dangling resources cleaned${NC}"
else
    echo -e "${YELLOW}Skipped dangling resources cleanup${NC}"
fi
echo ""

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}  Cleanup completed successfully!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo -e "${YELLOW}Summary:${NC}"
echo -e "  - All project containers stopped and removed"
echo -e "  - All project volumes removed"
echo -e "  - All project networks removed"
echo ""
echo -e "${YELLOW}To rebuild the ecosystem, run:${NC}"
echo -e "  docker-compose up -d"
echo ""
