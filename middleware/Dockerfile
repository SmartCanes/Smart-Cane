# Use lightweight Node.js image
FROM node:18-alpine

# Set working directory
WORKDIR /app

# Copy package.json and install dependencies
COPY package.json package-lock.json* ./
RUN npm install --production

# Copy source code
COPY middleware.js .

# Expose nothing (only MQTT + GraphHopper are used)
# but we could EXPOSE 3000 if you add a healthcheck endpoint

# Default command
CMD ["npm", "start"]
