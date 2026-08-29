FROM node:24-bookworm-slim AS builder

ENV PNPM_HOME="/pnpm"
ENV PATH="${PNPM_HOME}:${PATH}"
WORKDIR /workspace
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY web/package.json ./web/package.json
COPY extension/package.json ./extension/package.json
RUN pnpm install --frozen-lockfile
COPY contracts ./contracts
COPY web ./web
RUN pnpm web:build

FROM nginx:1.31-alpine
COPY web/nginx-main.conf /etc/nginx/nginx.conf
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /workspace/web/dist /usr/share/nginx/html
EXPOSE 8080
USER nginx
