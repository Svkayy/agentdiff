FROM node:20-slim AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
ARG VITE_CLERK_PUBLISHABLE_KEY
ARG VITE_AGENTDIFF_API_URL=http://localhost:8000
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY
ENV VITE_AGENTDIFF_API_URL=$VITE_AGENTDIFF_API_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
