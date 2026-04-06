# Contexto Codex — Organização e Separação Modular (`market_orchestrator`)

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

## Diagnóstico atual - resumo
O desenho atual está tecnicamente sólido e coerente com um modelo profissional de multiambiente. A governança dos compose foi bem executada: cada arquivo tem papel definido, com fronteiras claras. A operação de homologação está madura e próxima do ideal de reprodutibilidade. 

O principal risco residual está concentrado na consistência dos arquivos de ambiente, o problema agora não é técnico de subida, é governança de configuração. Com muitos arquivos `.env` por ambiente e por serviço.

## Objetivo e Estratégias de Implementação

**Objetivo**  
Fechar o contrato de configuração dos arquivos de ambiente para eliminar duplicações, conflito de variáveis e risco de vazamento de segredo, mantendo execução previsível entre development, staging e production.

**Estratégia de implementação**  
Executar em 4 blocos:  
1. Governança de contratos por família de arquivo.  
2. Higienização dos arquivos ativos sem sufixo.  
3. Padronização de templates por ambiente.  
4. Validação operacional com regras automáticas.

---

## Erros Comuns Confirmados e Alinhamento Ideal

1. **Erro comum: arquivo ativo vira fonte de modelagem**  
Descrição: arquivos sem sufixo acabam recebendo edição manual e viram “verdade paralela”.  
Alinhamento ideal: arquivos sem sufixo são somente artefato ativo gerado, nunca fonte de definição.

2. **Erro comum: variáveis duplicadas em famílias diferentes**  
Descrição: a mesma variável aparece em common e no serviço, gerando precedência ambígua.  
Alinhamento ideal: uma variável tem dono único por contrato.

3. **Erro comum: crescimento sem taxonomia**  
Descrição: novos env entram sem regra e aumentam conflito entre times.  
Alinhamento ideal: cada família tem escopo fechado e lista permitida de variáveis.

4. **Erro comum: templates não refletem runtime real**  
Descrição: templates existem, mas execução consome outro conjunto de arquivos.  
Alinhamento ideal: script de carga gera exatamente os ativos lidos pelos compose.

5. **Erro comum: segredo real em arquivo ativo persistente**  
Descrição: segredos ficam em ativos como [ .env.common ](.env.common).  
Alinhamento ideal: ativo local pode existir, mas com política rígida de geração, rotação e validação pré-subida.

---

## Ações Corretivas Objetivas por Problema

1. **Segredo em ativo sem controle**  
Ação: transformar ativos em artefatos de geração e exigir pré-validação obrigatória antes de subir hml.

2. **Duplicação de variável entre arquivos**  
Ação: consolidar owner único e remover todas as cópias fora do owner.

3. **Conflito de precedência por múltiplos env_file**  
Ação: publicar ordem oficial de precedência e reduzir sobreposição entre famílias.

4. **Template de ambiente divergente do runtime**  
Ação: alinhar script de carga para gerar exatamente os arquivos consumidos pelos compose.

5. **Evolução sem padrão**  
Ação: criar checklist obrigatório de mudança de configuração para toda alteração de env.

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
