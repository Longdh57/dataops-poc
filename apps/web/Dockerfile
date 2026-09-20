# Multi-stage: target `dev` cho docker compose, `runner` cho Cloud Run.

FROM node:24-alpine AS base
WORKDIR /srv

FROM base AS deps
COPY package.json ./
RUN npm install

# --- dev: dung cho docker compose local ---
FROM base AS dev
COPY --from=deps /srv/node_modules ./node_modules
COPY . .
ENV PORT=3000
EXPOSE 3000
CMD ["npm", "run", "dev"]

# --- build ---
FROM base AS build
COPY --from=deps /srv/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- runner: anh mong cho Cloud Run ---
FROM node:24-alpine AS runner
WORKDIR /srv
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

COPY --from=build /srv/public ./public
COPY --from=build --chown=nextjs:nodejs /srv/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /srv/.next/static ./.next/static

USER nextjs
ENV PORT=3000
EXPOSE 3000
CMD ["node", "server.js"]
