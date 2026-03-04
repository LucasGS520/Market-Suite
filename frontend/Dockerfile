#Dockerfile para o frontend Market-Suite
FROM node:20-alpine AS builder
WORKDIR /app

#Habilitar corepack para pnpm
RUN corepack enable && corepack prepare pnpm@10.23.0 --activate

#Copiar arquivos de dependências
COPY package.json pnpm-lock.yaml ./

#Instalar dependências (cacheado enquanto package.json não mudar)
RUN pnpm install --frozen-lockfile

#Copiar código fonte
COPY . .

# Não executa build aqui — o dev server do Vite serve diretamente do src/

#Estágio de produção (para deploy futuro — não usado em dev)
FROM node:20-alpine AS production
WORKDIR /app

#Habilitar corepack para pnpm
RUN corepack enable && corepack prepare pnpm@10.23.0 --activate

#Copiar apenas os arquivos necessários
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package.json ./

#Instalar apenas serve para servir os arquivos estáticos
RUN pnpm add -g serve
EXPOSE 5173

#Servir a aplicação
CMD ["serve", "-s", "dist", "-l", "5173"]