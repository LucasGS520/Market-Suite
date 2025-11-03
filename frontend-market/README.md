# Frontend Market (projeto)

Este diretório contém um frontend em React + Vite + TypeScript para integração com o backend `market_alert`.

Objetivo: fornecer um ponto de partida iterável com autenticação, CRUD básico de monitorados, páginas de detalhe e script para gerar tipos a partir do OpenAPI do backend.

Pré-requisitos
- Node.js >= 18
- Backend `market_alert` rodando localmente (http://localhost:8000) para geração de tipos e integração.

Instalação (local)

```cmd
cd frontend-market
npm install
npm run dev
```

Gerar tipos a partir do OpenAPI

> Este projeto usa `openapi-typescript` para gerar tipos fortemente tipados. O comando abaixo consulta `http://localhost:8000/openapi.json`.

```cmd
npm run generate-types
```

Configurar API base

- Por padrão o client usa `http://localhost:8000`. Para mudar, crie um arquivo `.env` com a variável:

```
VITE_API_BASE=https://seu-backend
```

Testes

```cmd
npm test
```

Notas
- O arquivo `src/types/generated-api.ts` é inicialmente um placeholder. Rode `npm run generate-types` para sobrescrevê-lo com os tipos reais do backend.
- Use `react-hook-form` + `zod` para validação dos formulários.
