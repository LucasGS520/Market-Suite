# Guia de Integração e Testes - Frontend MarketAlert

Este documento descreve como integrar e testar o frontend MarketAlert com o backend `market_alert`.

## Pré-requisitos

1. **Backend `market_alert` rodando** em `http://localhost:8000`
2. **Frontend `frontend-market` rodando** em `http://localhost:3000`
3. **Banco de dados PostgreSQL** configurado e acessível
4. **Redis** para Celery (se usando tasks assíncronas)

## Configuração de Ambiente

### Frontend

Crie um arquivo `.env.local` na raiz do projeto `frontend-market`:

```env
# URL da API do backend
VITE_FRONTEND_FORGE_API_URL=http://localhost:8000

# Configurações da aplicação
VITE_APP_TITLE=MarketAlert
VITE_APP_LOGO=https://seu-logo-url
VITE_APP_ID=seu-app-id
VITE_OAUTH_PORTAL_URL=https://seu-oauth-portal
```

### Backend

Certifique-se de que o backend está configurado com:

```bash
# Variáveis de ambiente do backend
DATABASE_URL=postgresql://user:password@localhost/marketalert
REDIS_URL=redis://localhost:6379
SECRET_KEY=sua-chave-secreta
```

## Endpoints da API

O frontend utiliza os seguintes endpoints do backend:

### Autenticação

**POST /auth**
- Autentica o usuário com email e senha
- Retorna um token JWT
- Exemplo:
  ```bash
  curl -X POST http://localhost:8000/auth \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=usuario@email.com&password=senha"
  ```

### Produtos Monitorados

**GET /monitored**
- Lista todos os produtos monitorados do usuário
- Requer autenticação (Bearer token)
- Exemplo:
  ```bash
  curl -X GET http://localhost:8000/monitored \
    -H "Authorization: Bearer seu-token-aqui"
  ```

**POST /monitored/scrape**
- Agenda scraping de um novo produto
- Requer autenticação
- Body:
  ```json
  {
    "name_identification": "Farol Uno Mille Fire",
    "product_url": "https://www.mercadolivre.com.br/MLB-...",
    "target_price": 189.90
  }
  ```

### Concorrentes

**GET /competitors/{monitored_product_id}**
- Lista concorrentes de um produto monitorado
- Requer autenticação
- Exemplo:
  ```bash
  curl -X GET http://localhost:8000/competitors/uuid-do-produto \
    -H "Authorization: Bearer seu-token-aqui"
  ```

**POST /competitors/scrape**
- Agenda scraping de um concorrente
- Requer autenticação
- Body:
  ```json
  {
    "monitored_product_id": "uuid-do-produto",
    "product_url": "https://www.mercadolivre.com.br/MLB-..."
  }
  ```

### Alertas

**GET /alerts**
- Lista todos os alertas do usuário
- Requer autenticação

**POST /alerts/{alert_id}/read**
- Marca um alerta como lido
- Requer autenticação

**DELETE /alerts/{alert_id}**
- Deleta um alerta
- Requer autenticação

### Dashboard

**GET /dashboard/stats**
- Retorna estatísticas do dashboard
- Requer autenticação
- Resposta:
  ```json
  {
    "total_monitored": 3,
    "active_alerts": 1,
    "ok_prices": 2,
    "potential_savings": 45.20
  }
  ```

## Testes Manuais

### 1. Teste de Autenticação

1. Abra o frontend em `http://localhost:3000`
2. Na página de login, insira credenciais válidas
3. Verifique se o token é armazenado no localStorage
4. Verifique se você é redirecionado para o dashboard

**Esperado:** Login bem-sucedido, redirecionamento para dashboard

### 2. Teste de Listagem de Produtos

1. Após fazer login, clique na aba "Produtos"
2. Verifique se a lista de produtos é carregada
3. Verifique se cada produto mostra nome, preço, status e concorrentes

**Esperado:** Lista de produtos carregada corretamente

### 3. Teste de Adição de Produto

1. Clique na aba "Adicionar"
2. Preencha o formulário com:
   - Nome: "Teste Produto"
   - URL: "https://www.mercadolivre.com.br/MLB-123456789"
   - Preço Alvo: "100.00"
3. Clique em "Adicionar Produto"

**Esperado:** Produto adicionado com sucesso, redirecionamento para produtos

### 4. Teste de Visualização de Concorrentes

1. Na página de produtos, clique em "Ver Concorrentes" para um produto
2. Verifique se a lista de concorrentes é carregada
3. Clique em "Ver Anúncio do Concorrente"

**Esperado:** Página de concorrentes carregada, link abre em nova aba

### 5. Teste de Alertas

1. Clique no ícone de sino no header
2. Verifique se os alertas são carregados
3. Clique no ícone de verificação para marcar como lido
4. Clique no ícone de lixeira para deletar

**Esperado:** Alertas carregados, ações funcionando

### 6. Teste de Logout

1. Clique no ícone de usuário no header
2. Clique em "Sair"
3. Verifique se você é redirecionado para login
4. Verifique se o token é removido do localStorage

**Esperado:** Logout bem-sucedido, redirecionamento para login

## Testes Automatizados

### Executar Testes TypeScript

```bash
pnpm check
```

### Executar Testes com Vitest (quando implementados)

```bash
pnpm test
```

## Troubleshooting

### Erro: "Falha na autenticação"

**Causa:** Credenciais inválidas ou backend não respondendo

**Solução:**
1. Verifique se o backend está rodando em `http://localhost:8000`
2. Verifique as credenciais no banco de dados
3. Verifique a URL da API em `.env.local`

### Erro: "Erro ao buscar produtos"

**Causa:** Token expirado ou permissões insuficientes

**Solução:**
1. Faça logout e login novamente
2. Verifique se o usuário tem produtos cadastrados
3. Verifique os logs do backend

### Erro: "CORS"

**Causa:** Backend não está configurado para aceitar requisições do frontend

**Solução:**
1. Verifique a configuração de CORS no backend
2. Adicione `http://localhost:3000` aos origins permitidos
3. Reinicie o backend

### Erro: "Conexão recusada"

**Causa:** Backend não está rodando

**Solução:**
1. Inicie o backend: `python market_alert/main.py`
2. Verifique se está rodando em `http://localhost:8000`
3. Verifique os logs do backend

## Fluxo de Integração Completo

1. **Usuário faz login** → Frontend envia credenciais → Backend retorna token JWT
2. **Frontend armazena token** → localStorage
3. **Usuário navega para Produtos** → Frontend busca produtos com token
4. **Backend retorna produtos** → Frontend exibe lista
5. **Usuário clica em "Adicionar"** → Frontend abre formulário
6. **Usuário preenche e submete** → Frontend envia dados com token
7. **Backend agenda scraping** → Retorna confirmação
8. **Frontend redireciona** → Mostra mensagem de sucesso
9. **Celery processa** → Scraping é executado
10. **Dados são atualizados** → Frontend refetch quando usuário retorna

## Monitoramento

### Logs do Frontend

Verifique o console do navegador (F12) para erros JavaScript e requisições HTTP.

### Logs do Backend

```bash
# Ver logs do backend
tail -f market_alert/logs/app.log
```

### Verificar Requisições HTTP

Use as DevTools do navegador (F12 → Network) para inspecionar requisições HTTP.

## Performance

### Otimizações Implementadas

- **Code splitting:** Vite carrega componentes sob demanda
- **Lazy loading:** Páginas são carregadas quando necessário
- **Caching:** Dados são cacheados no localStorage
- **Debouncing:** Requisições são debounced para evitar múltiplas chamadas

### Métricas

- **Tempo de carregamento inicial:** < 3 segundos
- **Tempo de resposta da API:** < 1 segundo
- **Tamanho do bundle:** < 500 KB (gzipped)

## Próximas Melhorias

- [ ] Implementar testes E2E com Cypress
- [ ] Adicionar testes unitários com Vitest
- [ ] Implementar cache com Service Worker
- [ ] Adicionar offline mode
- [ ] Implementar WebSocket para atualizações em tempo real

## Suporte

Para dúvidas ou problemas, verifique:

1. `README.md` - Documentação geral
2. `userGuide.md` - Guia de uso
3. Logs do frontend e backend
4. Issues no repositório GitHub
