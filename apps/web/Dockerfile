# OCL Agent web (Next.js standalone)
FROM node:24-alpine AS deps
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:24-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web ./
# baked into the client bundle: browser -> API through the same Caddy origin
ARG NEXT_PUBLIC_API_BASE=""
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm run build

FROM node:24-alpine AS run
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S ocl && adduser -S ocl -G ocl
COPY --from=build --chown=ocl:ocl /app/.next/standalone ./
COPY --from=build --chown=ocl:ocl /app/.next/static ./.next/static
COPY --from=build --chown=ocl:ocl /app/public ./public
USER ocl
EXPOSE 3000
CMD ["node", "server.js"]
