FROM node:20-slim

WORKDIR /app

# Copy the lockfile too, and use `npm ci` rather than `npm install`.
#
# `npm install` re-resolves the dependency tree and can pull different
# versions than the ones tested — the same class of bug that broke the
# backend in Phase 15, where the container resolved a newer httpx than
# the test environment. `npm ci` installs exactly what the lockfile
# specifies and fails loudly if package.json and the lock disagree.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
