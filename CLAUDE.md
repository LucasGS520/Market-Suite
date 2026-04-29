# Claude — Contexto e Objetivos

## Sobre o Projeto *Market Suite* (`market_suite`)
**MarketSuite** é uma plataforma de monitoramento e comparação de preços em e-commerce. Usuários cadastram produtos que desejam acompanhar, o sistema coleta informações de preço e disponibilidade automaticamente, compara com concorrentes e dispara notificações quando mudanças significativas são detectadas.

O projeto é separado por responsabilidades, em diferentes módulos:
**Backend**:
- **API + Persistência** (market_alert): Gerencia estado de usuários, produtos, comparações
- **Scraping especializado** (market_scraper): Extrai dados de e-commerce via HTTP
- **Processamento em background** (Celery + Redis): Coleta, comparação e notificações assíncronas
- **Orquestração durável** (market_orchestrator): Ciclo de vida contínuo de monitoramento por produto com Temporal.

**Frontend**:
- **SPA moderna**: consome API backend via HTTP (REST/JSON).

> Informações sobre a Stack e Tecnologias existentes em [STACK_MARKET.md](STACK_MARKET.md)

---

## **Diagnóstico Scraper Atual**

O `market_scraper` está **operacional no nível de API**, mas **não está funcional como scraper de produto** no teste registrado. O serviço sobe, expõe `/docs` e `/openapi.json`, inicializa o HTTP collector e tenta iniciar o browser collector; porém, após as requisições reais, **não houve nenhuma resposta 200 com produto extraído** no log enviado .

O `market_scraper` não está mais degradado por falha de startup. Agora ele está **funcional em infraestrutura**, mas **não está funcional em extração**.

O gargalo atual é a navegação/renderização com Playwright contra páginas do Mercado Livre.

Causas prováveis, com base no log:

1. **Timeout de renderização insuficiente ou mal coordenado**
   O wrapper reporta timeout após `25s`, enquanto aparece exceção interna de Playwright com quase `60s`. Isso indica possível conflito entre timeout externo, timeout do Crawlee e timeout de navegação do Playwright.

2. **Resposta anti-bot do Mercado Livre**
   Em uma das requisições houve detecção explícita de `mercadolivre_challenge`. Nesse cenário, o browser pode receber uma página válida do ponto de vista HTTP, mas inválida para scraping.

3. **Condição de espera inadequada**
   O Playwright está aguardando navegação/carregamento até `domcontentloaded` em pelo menos uma falha. Em páginas pesadas ou com challenge, trackers, recursos bloqueados ou navegação client-side, essa espera pode nunca concluir dentro do limite.

4. **Coleta parcial sem aproveitamento**
   O log mostra `browser_fetch_success html_size=35030`, mas o pipeline ainda descarta o resultado por timeout posterior. Isso indica que o scraper talvez precise encerrar a coleta assim que obtiver HTML útil, em vez de depender da conclusão completa do fluxo de navegação.

---

## Regras e Instruções de Execução
**Regras obrigatórias de economia (NÃO IGNORAR)**
1) NÃO liste árvore inteira do projeto (evite `tree`, `ls -R`, etc.). Se precisar, liste apenas pastas-alvo da FASE.
2) NÃO leia arquivos completos. Leia no máximo 120 linhas por arquivo (ou trechos específicos). Se precisar de mais contextualização, peça antes.
3) Priorize busca (rg/grep) para localizar pontos de mudança antes de abrir arquivos.
5) Não cole conteúdo integral de arquivos na resposta. Mostre apenas:
   - arquivos alterados
   - resumo do diff (o que mudou e por quê)
   - comandos executados e resultados
6) Execute somente UMA FASE por vez. Ao terminar a FASE:
   - pare e peça autorização para a próxima FASE
7) Se detectar duplicação/overreach fora do escopo, interrompa e reporte.
