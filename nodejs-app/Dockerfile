FROM node:20-alpine

# Install health check dependencies (wget is already in alpine, but being explicit)
RUN apk add --no-cache wget

# Create app directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy application code
COPY . .

# Expose port
EXPOSE 3000

# Start application
CMD ["npm", "start"]