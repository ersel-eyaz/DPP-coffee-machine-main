# dpp-frontend/Dockerfile
FROM node:20-alpine
WORKDIR /app

# Install deps
COPY package.json package-lock.json* ./
RUN npm ci

# Copy sources
COPY . .

# Make sure Vite binds to all interfaces inside the container
ENV HOST=0.0.0.0

# Let the app know where the backend is (compose service name)
# You can also set this in docker-compose under 'environment' if you prefer.
ENV VITE_API_URL=http://backend:8000

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
