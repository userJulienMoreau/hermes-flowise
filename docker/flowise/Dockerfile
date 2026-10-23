# Image Flowise + nœuds Hermes. Contexte de build : racine du dépôt.
ARG FLOWISE_IMAGE_TAG=3.1.3

FROM node:20-alpine AS build
WORKDIR /nodes
COPY nodes/package.json nodes/package-lock.json ./
RUN npm ci
COPY nodes/ ./
RUN npm run build

FROM flowiseai/flowise:${FLOWISE_IMAGE_TAG}
# Flowise ne charge les nœuds et credentials que depuis le dossier dist de flowise-components
# (packages/server/src/NodesPool.ts : pas de variable d'environnement pour un autre chemin).
COPY --from=build /nodes/build/ /usr/local/lib/node_modules/flowise/node_modules/flowise-components/dist/
