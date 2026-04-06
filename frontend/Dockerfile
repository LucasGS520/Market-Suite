#Dockerfile para o frontend Market-Suite
FROM node:20-alpine AS builder
WORKDIR /app

#Habilitar corepack para pnpm
RUN corepack enable && corepack prepare pnpm@10.23.0 --activate

#Copiar arquivos de dependências
COPY frontend/package.json frontend/pnpm-lock.yaml ./

#Instalar dependências (cacheado enquanto package.json não mudar)
RUN pnpm install --frozen-lockfile

#Copiar código fonte
COPY frontend ./

# Build de produção — VITE_API_URL obrigatório; falha explicitamente se ausente
ARG VITE_API_URL
RUN if [ -z "$VITE_API_URL" ]; then \
      echo "ERRO: VITE_API_URL não definido. Passe --build-arg VITE_API_URL=https://api.seudominio.com"; \
      exit 1; \
    fi
ENV VITE_API_URL=${VITE_API_URL}
RUN pnpm run build

# ---- Estágio de produção — apenas artefatos estáticos, sem código-fonte ou devDependencies
# FROM node:20-alpine AS production
# WORKDIR /app

# RUN corepack enable && corepack prepare pnpm@10.23.0 --activate

# COPY --from=builder /app/dist ./dist
# COPY --from=builder /app/package.json ./

# RUN pnpm add -g serve
# EXPOSE 5173

# CMD ["serve", "-s", "dist", "-l", "5173"]