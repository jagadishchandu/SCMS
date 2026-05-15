# ============ Build stage ============
# Build context is the `frontend/` directory itself.
# Usage:
#   cd frontend && docker build -t scms-frontend .
# Or from repo root via docker-compose (see docker-compose.yml).

FROM node:20-alpine AS build

WORKDIR /app

# Allow overriding the backend URL at build time:
#   docker build --build-arg REACT_APP_BACKEND_URL=https://api.example.com -t scms-frontend .
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

# Install deps (cached layer)
COPY package.json yarn.lock* ./
RUN yarn install --frozen-lockfile || yarn install

# Build
COPY . .
RUN yarn build

# ============ Runtime stage ============
FROM nginx:alpine

# wget is used for the container healthcheck
RUN apk add --no-cache wget

COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3000/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
