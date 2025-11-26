# Especificação Final de Frontend (V3.0) - MarketAlert

**Objetivo:** Guia de desenvolvimento definitivo para o Frontend do MarketAlert, consolidando o design visual (baseado no modelo de referência), o fluxo de dados (integrando a API modificada) e a experiência do usuário (UI/UX).

---

## 1. Princípios de Design e Experiência do Usuário (UI/UX)

O design do MarketAlert deve ser **moderno, profissional e focado em dados**, seguindo o tema **Light/Dark Mode**. O sistema deve ser simples, fácil de usar e focado em comparação, monitoramento de preços e alertas para alavancar a competitividade do vendedor

**Regras de Negócio e Requisitos Funcionais**
- **Foco em competitividade**:
  - O sistema deve ser visualmente orientado para alertas e competitividade.
  - O status de competitividade (Atenção, Competitivo, Não Competitivo, Urgente) deve ser um indicar visual.
  - O design deve priorizar cores de status (Vermelho/Amarelo/Verde) e filtros por status.
- **Comparação automática**:
  - As comparações são processadas exclusivamente pelo backend. O usuário não pode forçar uma nova comparação.
  - O botão de "Atualizar" ou "Forçar Comparação" deve ser removido da UI, sem possibilidade de comparação manual.
- **Adição Simples de Produto**:
  - O fluxo de adição de produtos monitorados e concorrentes deve ser feito através de uma URL única.
  - Implementar um modal/página de "Adicionar Produto" com um campo de URL e feedback assíncrono (polling).
  - Seguir o mesmo conceito para a adição de produtos concorrentes, com feedback visual claro para qual monitorado os concorrentes estão sendo inseridos, evitando erros de adição a produtos errados pelo usuário.
- **UX/UI Profissional**:
  - O design deve ser otimizado para uma experiência de usuário profissional e intuitiva


### 1.1. Paleta de Cores e Tipografia Geral do Sistema

| Elemento | Cor (Função) | Uso |
| :--- | :--- | :--- |
| **Fundo Principal** | Modo Dark/Light Mode | Fundo da aplicação e da maioria dos cards. |
| **Fundo Secundário** | Tom mais claro (dependendo da versão Light ou Dark Mode) | Fundo de cards, ou elementos de contraste. |
| **Ação/Destaque** | Vibrante | Botões de ação primária ("Ver Detalhes", "Adicionar Produto"). |
| **Competitivo (Sucesso)** | Verde | Indicadores de preço competitivo (Ranking #1, Diferença Negativa). |
| **Atenção (Alerta)** | Amarelo | Indicadores de preço não competitivo (Ranking baixo, Diferença Positiva). |
| **Urgente (Risco)** | Vermelho | Indicadores de preço muito alto ou erro de monitoramento. |
| **Tipografia** | Fonte *Sans-serif* limpa | Uso de pesos e tamanhos variados para hierarquia visual. |

### 1.2. Páginas Essenciais 
| Página | URL Sugerida | Função Principal | Navegação |
| :--- | :--- | :--- | :--- |
| **Login/Registro** | `/login`, `/register` | Autenticação e criação de conta. | Fora do layout principal. |
| **Barra Superior** | N/A | Contém o logo, atalhos para as páginas principais e ícone de Perfil/Configurações. | Persistente |
| **Dashboard** | `/dashboard` | Página inicial, resumo de métricas e produtos em destaque (mais relevantes). | Atalho na barra superior |
| **Produtos** | `/products` |  Visualização e gestão de todos os produtos monitorados (modo de visualização em Lista e Tabela). | Atalho na barra superior |
| **Detalhes do Produto** | `/product/:id` | Análise individual, concorrentes, histórico e gestão de alertas. | Acesso via Dashboard ou Produtos |
| **Comparação** | `/compare` | Análise comparativa e competitiva de múltiplos produtos. | Atalho na Barra Superior. |
| **Alertas e Notificações** | `/alerts` | Histórico de alertas e notificações já enviadas. | Atalho na Barra Superior. |
| **Configurações e Perfil** | `/settings` | Gerenciamento de dados do usuário e regras de alerta. | Ícone de Perfil na Barra Superior. |

### 1.3. Estrutura e Navegação (Header)

A navegação principal será feita através de uma **Barra de Navegação Superior** (Header) persistente, que oferece acesso rápido às páginas centrais da aplicação

| Item de Navegação | URL | Ícone | Função |
| :--- | :--- | :--- | :--- |
| **Logo/Marca** | `/dashboard` | Logo do MarketAlert | Retorna à página inicial. |
| **Dashboard** | `/dashboard` | Ícone de Casa/Gráfico | Visão geral e destaques. |
| **Produtos** | `/products` | Ícone de Lista/Tabela | Gestão de produtos monitorados. |
| **Comparação** | `/compare` | Ícone de Balança/Gráfico | Análise comparativa. |
| **Alertas** | `/alerts` | Ícone de Sino/Alerta | Histórico e gestão de alertas. |
| **Perfil/Configurações** | `/settings` | Ícone de Usuário/Engrenagem | Acesso a configurações e logout. |

---

## 2. Fluxo de Dados e Integração com a API

O frontend deve consumir a API do backend **após as modificações propostas** (V1.0), garantindo o tratamento correto dos dados.

### 2.1. Dashboard (`/dashboard`)
- **Função:** Visão Geral imediata das métricas e destque dos produtos que exigem mais atenção

| Elemento (UI) | Endpoint (API) | Campo(s) Consumido(s) | Tratamento de Dados (Frontend) |
| :--- | :--- | :--- | :--- |
| **Cards de Resumo** | `GET /dashboard/stats` | `total_monitored`, `active_alerts`, `ok_prices`, `total_competitors` | Exibir valores numéricos formatados. |
| **Produtos em Destaque** | `GET /monitored/featured` | Endpoint que retorna produtos mais relevantes | Renderizar cards de produto (semelhantes à Vista em Lista) com destaque visual. |
| **Botão "Adicionar Produto** | `POST/ monitored/scrape` | `product_url`, opcional `name_identification` | *Assíncrono* Frontend deve gerenciar o estado de "processando" e usar polling para atualizar a lista. |


### 2.2. Produtos (`/products`)
- **Função:** Gestão e visualização detalhada de todos os produtos monitorados, com opções de busca e filtro, opções de vista em Lista ou Tabela

| Elemento (UI) | Endpoint (API) | Campo(s) Consumido(s) | Tratamento de Dados (Frontend) |
| :--- | :--- | :--- | :--- |
| **Botão Adicionar Produto** | `POST /monitored/scrape` | `product_url`, opcional `name_identification` | 
| **Busca/Filtro** | `GET /monitored` | `query`, `status` (parâmetros) | Enviar parâmetros para o backend e re-renderizar a lista. |
| **Tabela/Lista** | `GET /monitored?query=...&status=...` | `MonitoredProductResponse` + `PriceComparisonSummaryResponse` | *Lógica de Status:* Comparar `competitors_min` com `monitored_price` (ambos como `Decimal`) para definir a cor do status (Verde/Amarelo/Vermelho). |
| **Dados de Competitividade** | `GET/ comparisons/{monitored_id}/summary` | `monitored_price`, `competitors_min`, `position_rank` | Demonstrar esses valores, e que mudem conforme visualização em modo lista e modo tabela |
| **Botão "Ver Detalhes"** | Navegação | `/product/:id` | Redirecionar para a página de detalhes. | *Assíncrono* Frontend deve gerenciar o estado de "processando" e usar polling para atualizar a lista. |

#### Modo Lista (Produtos - Visto em Lista) A versão de modo *lista* deve ser visualmente assim [`modo_lista.png`](modo_lista.png)
A visualização em "Lista" serve como um Painel de Controle para o vendedor, apresentando uma visão geral e imediata do status de monitoramento de preços de seus produtos. 
Foco em *visibilidade rápida* de produtos que requerem atenção e na comparação direta do preço do "MEU PREÇO" com o "MENOR CONCORRENTE".

* **Ações Executaveis**
- No topo da página de "Produtos":
 - Botão "Adicionar Produto" com fundo no tom mais claro que o principal (dependendo do Mode) para criar contraste, com bordas arrendodadas e sombra sutil para profundidade, 
 - Botões/Campo de Busca e filtro, alinhado com botão de "Adicionar Produto" 
 - Botão alinhado ao "Adicionar Produto" para mudar visualização da página para Lista ou Tabela
- Atribuido ao "Card de Produto":
 - Botão "Ver Detalhes" com cor em detaque no canto inferior direito do card. Função de navegar para a página de detalhes de produto.

* **Cards de Produto (Lista)**
- Formato do Card: Retangular, com fundo no tom mais claro que o principal (dependendo do Mode) para criar contraste, com bordas arredondadas e sombra sutil para profundidade
- Informações Contidas:
 - Imagem: Miniatura quadrada no canto superior esquerdo
 - Título do Produto: Nome de identificação ou Nome do item
 - Origem: Marketplace (futuramente nome da loja)
 - Status (Tag): Um pequeno Badge colorido no canto superior direito indicando status (ex: "Atenção" - Amarelo, "Não Competitivo" - Amarelo, "Competitivo" - Verde, "Urgente" - Vermelho)
- Comparativo de Preços (3 Colunas):
 - MEU PREÇO: Preço atual do vendedor (detacado)
 - MENOR CONCORRENTE: Menor preço encontrado (detacado, diferente do "MEU PREÇO")
 - DIFERENÇA: Valor e ícone de tendência (seta para cima/baixo) indicando a diferença de preço (detaque em vermelho/verde dependendo da diferença)
- Ranking de Concorrentes: Informação de posição no ranking de preços (ex: "Ranking #3 de 5") e contagem de concorrentes (ex: "4 concorrentes")

* **Detalhes técnicos simplificados**
- *Responsividade*: O layout dos cards de resumo (topo) deve ser responsivo, provavelmente empilhando em telas menores (mobile). Os cards de produto parecem ocupar a largura total disponível.
- *Tipografia*: Fonte limpa e moderna (provavelmente sans-serif), com pesos e tamanhos variados para hierarquia (título do produto maior, métricas em destaque, descrições menores).
- *Quantidade por página*: Exibir 5 produtos por página no modo visualização em Lista

#### Modo Tabela (Produtos - Visto em Tabela) A versão de modo *tabela* deve ser visualmente assim [`modo_tabela.png`](modo_tabela.png)
O modo de visualização em "Tabela" oferecer uma visão mais ampla dos produtos monitorados, facilitando a comparação direta entre eles, ideal para análise rápida e de grandes volumes.

* **Ações Executaveis**
- No topo da página de "Produtos":
 - Botão "Adicionar Produto" com fundo no tom mais claro que o principal (dependendo do Mode) para criar contraste, com bordas arrendodadas e sombra sutil para profundidade, 
 - Botões/Campo de Busca e filtro, alinhado com botão de "Adicionar Produto" 
 - Botão alinhado ao "Adicionar Produto" para mudar visualização da página para Lista ou Tabela
- Atribuido ao "Card de Produto":
 - Botão "Ver Detalhes" com cor em detaque no canto inferior direito do card. Função de navegar para a página de detalhes de produto.

* **Tabela com Produtos Monitorados**
A tabela é o elemento central e possui as seguintes colunas principais:
| Coluna | Conteúdo | Destaque Visual | Ações Executáveis |
| :--- | :--- | :--- | :--- |
| **Produto** | Miniatura da Imagem do produto | Miniatura a esquerda | Visualizavel |
| **Meu Preço** | Preço de venda atual do produto monitorado | Valor em destaque | Visualizavel | 
| **Menor Concorrente** | O preço mais baixo encontrado entre os concorrentes | Valor em Destaque | Visualizavel |
| **Diferença** | A diferença de preço (Meu preço - Menor Concorrente) | 
Positivo: Texto em vermelho (prejuízo/não competitivo). Negativo: Texto em verde (competitivo). | Ordenação: Para ordenar de forma crescente ou decrescente | 
| **Concorrentes** | Número total de concorrentes monitorados para o produto | Texto Simplies | Visualizavel |
| **Ranking** | Posição do preço do usuário no ranking total de preços | Texto simples (ex: #1 de 6) | Visualizavel |
| **Status** | Status de competitividade (Atenção, Não Competitivo, Competitivo, Urgente) | Um pequeno circulo ou badge colorido (semelhante ao modo lista) | Visualizavel |
| **Ações** | Botão "Ver Detalhes" | Botão "Ver" | Executável: Navegar para a página de detalhes do produto |

* **Detalhes técnicos simplificados**
- *Responsividade*: A tabela deve ser responsivo com mobile, em telas menores, a tabela pode precisar de rolagem horizontal ou uma adaptação para exibir os dados de forma empilhada (como cards), mas no desktop, ela ocupa a largura total.
- *Estrutura da tabela*: A tabela deve ser construída com linhas alternadas ou um leve hover de cor para melhorar leitura
- *Alinhamento*: Os dados de preço (Meu Preço, Menor Concorrente, Diferença) estão alinhados à direita para facilitar a comparação numérica. Outras colunas estão alinhadas à esquerda ou centralizadas.
- *Tipografia*: Fonte limpa e moderna (provavelmente sans-serif), com pesos e tamanhos variados para hierarquia (título do produto maior, métricas em destaque, descrições menores).
- *Quantidade*: Exibir todos os produtos na tabela, contendo tudo em uma única página.


### 2.3. Detalhes do Produto (`/product/:id`)
- **Função:**  Análise aprofundada de um único produto.

| Elemento (UI) | Endpoint (API) | Campo(s) Consumido(s) | Tratamento de Dados (Frontend) |
| :--- | :--- | :--- | :--- |
| **Informações Principais** | `GET/ monitored/{product_id}` | `name`, `product_url`, `current_price`, `thumbnail` | Traz as informações principais sobre o produto monitorado |
| **Resumo de Preços/Comparações** | `GET /comparisons/{id}/summary` | `monitored_price`, `competitors_min`, `position_rank`, `potential_savings` (todos como `Decimal`) | Calcular e exibir a diferença de preço. Formatar valores como moeda (R$). |
| **Insights de Comparação** | `GET /comparisons/{id}/summary` | `comparison_insights` | Exibir o texto de sugestão/insights das comparações realizadas. |
| **Histórico (Gráfico)** | `GET /comparisons/{id}` | `timestamp`, `data` | Plotar gráfico de linha usando os dados de preço e tempo. |
| **Lista de Concorrentes** | `GET /competitors?monitored_id={id}` | `CompetitorProductResponse` | Exibir nome, preço e informações sobre concorrentes. |
| **Botão "Adicionar Concorrentes"** | `POST/ competitors/scrape` | `monitored_product_id`, `product_url` | *Assíncrono*  Requer o monitored_product_id do produto pai, Frontend deve gerenciar o estado de "processando". |

#### Layout e Design
Está página é o *centro de controle e análise aprofundada* de um único produto monitorado, sua função é fornecer todos os detalhes de preço, concorrência, histórico e sugestões de ação para que o usuário.
- Estrutura: O layout é baseado em um sistema de blocos disposto em colunas (provalvelmente duas colunas em desktop), organizando as informações de forma modular e hierárquica
- Design: Mantém estrutura padrão de cores e o estilo de cards arredondados, uso de cores estratégico para destacar informações.
- Cabeçalho: Contém título do produto, a origem, botões de ação globais no canto superior direito e "seta" para retornar a página de produtos.

* **Informações e Blocos Existentes**
A página é composta por vários blocos:
| Bloco | Conteúdo Principal | Destaque Visual | Ações Executáveis |
| :--- | :--- | :--- | :--- |
| **Informações Básicas e Preços** | Imagem do produto, Título, Status (Tag), MEU PREÇO e MENOR CONCORRENTE (em blocos de cor). | Destaque de preço em fonte grande. Cores de status. | Visualizavel |
| **Insights de Comparação** | Sugestão de preço e análise da diferença de preço em relação ao concorrente. | Fundo em cor de destaque para chamar a atenção. | Visualizavel | 
| **Ações Rápidas** | Botões para ações imediatas relacionadas ao produto monitorado. | Botões empilhados para "Adicionar Concorrente", "Pausar Monitoramento", "Remover Produto". | Executáveis: Adicionar Concorrente, Pausar, Remover. |
| **Comparação de Preços** | Métricas chave: Diferença de Preço, Meu Ranking, Total Concorrentes, Concorrente Min e Max. | 
Valores em destaque, com cores indicativas (vermelho/verde para Diferença). | Visualizavel | 
| **Todos os Concorrentes** | Lista detalhada de cada concorrente: Nome, Preço e Marketplace | informações sobre concorrentes para visualização | Visualizavel |
| **Histórico de Preços** | Gráfico | Visualização de dados (Gráfico). | Alterar modo de exibição do Gráfico (linha, em barra, etc) |
| **Estatísticas** | Dados de monitoramento: Última atualização, Monitorando desde, | Informações em formato de lista simples. | Visualizavel |

* **Detalhes técnicos simplificados**
- *Blocos*: Todos os blocos de informação devem ser apresentados com cantos arredondados, mantendo a consistência visual.
- *Botões*: Botões de ação retangulares, com cantos arredondados, botões de "Ações Rápidas" são grandes e empilhados verticalmente, facilitando clique 
- *Hierarquia Visual*: O título do produto e os blocos de preço (Meu Preço / Menor Concorrente) são os elementos de maior destaque visual.
- *Disposição*: A disposição em duas colunas (Informações/Preços à esquerda, Insights/Ações Rápidas/Estatísticas à direita) otimiza o uso do espaço em telas largas.


### 2.4. Alertas e Notificações (`/alerts`)
- **Função:** Visualizar histórico de notificações e gerenciar regras de alerta

| Elemento (UI) | Endpoint (API) | Campo(s) Consumido(s) | Tratamento de Dados (Frontend) |
| :--- | :--- | :--- | :--- |
| **Histórico de Notificações** | `GET /notifications/logs` | `NotificationLogResponse` | Visualizar e acompanhar notificações e alertas já enviados |

---

## 3. Requisitos de Implementação e UX/UI

### 3.1. Tratamento de Dados e Formatação

1.  **Valores Numéricos:** Todos os valores de preço (`monitored_price`, `competitors_min`, `potential_savings`, etc.) devem ser tratados como `Decimal` ou `float` (conforme a API modificada) e formatados para a moeda brasileira (R$ 0.000,00) antes da exibição.
2.  **Lógica de Status:**
    *   **Competitivo (Verde):** `monitored_price` <= `competitors_min`.
    *   **Atenção (Amarelo):** `monitored_price` > `competitors_min` por uma margem aceitável (lógica a ser definida, ex: até 4% de diferença).
    *   **Urgente (Vermelho):** `monitored_price` > `competitors_min` por uma margem alta (ex: acima de 4% de diferença).
3.  **Data/Hora:** Todos os campos de data/hora (`last_comparison_at`, `collected_at`) devem ser formatados para o padrão brasileiro (DD/MM/AAAA HH:MM).


### 3.2. Fluxo de Adição de Produto Monitorado e Concorrente (UX Otimizado)

O fluxo de adição de produto monitorado ou concorrente deve ser o mais suave possível:

1.  **Input:** Um campo de texto simples para a URL (nome opcional se for monitorado).
2.  **Feedback Imediato (202 Accepted):** Após o envio, o frontend deve exibir uma notificação *toast* ou *banner* informando: "Produto em processamento. Ele aparecerá na sua lista em breve."
3.  **Polling:** O frontend deve iniciar um *polling* silencioso (ex: a cada 5-10 segundos) no endpoint `GET /monitored` ou `GET /competitors` para detectar a criação do produto.
4.  **Feedback Final:** Quando o produto for detectado, exibir uma notificação de sucesso: "Produto [Nome do Produto] adicionado com sucesso!"

**OBS: Para produtos concorrentes, devem possuir um feedback visivel com informações sobre o produto monitorado no qual o concorrente esta sendo atribuido, evitando erros de adição a produtos monitorados errados quando usuário estiver utilizando o sistema**


### 3.3. Tratamento de Erros (UX)

O tratamento de erros deve ser amigável e informativo:

| Código de Erro (API) | Mensagem de Erro (Frontend) | Ação Sugerida ao Usuário |
| :--- | :--- | :--- |
| **409 Conflict** | "Este produto já está sendo monitorado." | Redirecionar para a página de detalhes do produto existente. |
| **429 Too Many Requests** | "Limite de requisições de monitoramento atingido. Tente novamente em [X] minutos." | Exibir o tempo de espera e desabilitar o botão de envio temporariamente. |
| **400 Bad Request** | "URL inválida ou não suportada. Verifique o endereço e tente novamente." | Destacar o campo de URL e manter o modal aberto. |
| **Erros de Scraping** | "Ocorreu um erro ao coletar os dados do produto. Verifique a página de Alertas para mais detalhes." | Exibir link para a página `/alerts`. |

---

## 4. Conclusão

Este documento, em conjunto com a **Especificação de Modificações de Backend (V1.0)**, fornece todas as informações necessárias para construir o Frontend do MarketAlert. O foco na consistência visual, na integração precisa com a API e na experiência do usuário garantirá um produto final de alta qualidade.
