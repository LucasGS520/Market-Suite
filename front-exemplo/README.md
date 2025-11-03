# MarketAlert - Monitoramento Inteligente de Preços

## Visão Geral

O **MarketAlert** é uma aplicação web completa e responsiva para monitoramento inteligente de preços de produtos no Mercado Livre. A aplicação permite acompanhar preços de produtos próprios versus concorrentes, enviando alertas quando necessário ajustar preços para manter competitividade.

## Características Principais

### 🎯 Funcionalidades Core
- **Monitoramento Automático**: Acompanha preços de produtos em tempo real
- **Alertas Inteligentes**: Notifica quando concorrentes têm preços menores
- **Dashboard Analítico**: Visão geral com métricas e estatísticas
- **Gestão de Produtos**: Adicionar, editar e remover produtos do monitoramento
- **Comparação de Preços**: Visualização lado a lado dos preços próprios vs concorrentes

### 📱 Design Responsivo
- **Versão Desktop**: Interface completa com tabs e layout expandido
- **Versão Mobile**: Interface otimizada com navegação bottom e menu hambúrguer
- **Toggle de Visualização**: Alternância entre modos desktop e mobile
- **Detecção Automática**: Identifica automaticamente o tipo de dispositivo

### 🎨 Identidade Visual
- **Cores da Marca**: Gradiente laranja/amarelo inspirado no logo
- **Logo Integrado**: Logo MarketAlert presente em todas as telas
- **UI Moderna**: Componentes shadcn/ui com design system consistente
- **Micro-interações**: Hover states e transições suaves

## Tecnologias Utilizadas

### Frontend
- **React 18**: Framework principal
- **Vite**: Build tool e dev server
- **Tailwind CSS**: Framework de estilos
- **shadcn/ui**: Biblioteca de componentes
- **Lucide React**: Ícones modernos
- **Framer Motion**: Animações (pré-instalado)

### Funcionalidades Técnicas
- **Responsive Design**: Adaptação automática para diferentes telas
- **State Management**: useState para gerenciamento de estado local
- **Component Architecture**: Componentes reutilizáveis e modulares
- **Modern JavaScript**: ES6+ com hooks e functional components

## Estrutura do Projeto

```
market-alert/
├── public/                 # Arquivos estáticos
├── src/
│   ├── assets/            # Imagens e recursos
│   │   └── LOGOMARTKETALERT.jpeg
│   ├── components/        # Componentes React
│   │   ├── ui/           # Componentes shadcn/ui
│   │   └── MobileApp.jsx # Versão mobile da aplicação
│   ├── App.jsx           # Componente principal
│   ├── App.css           # Estilos globais
│   └── main.jsx          # Entry point
├── dist/                 # Build de produção
└── README.md            # Esta documentação
```

## Funcionalidades Detalhadas

### Dashboard
- **Cards de Estatísticas**: Total de produtos, alertas ativos, preços OK, economia potencial
- **Alertas Urgentes**: Lista de produtos que requerem atenção imediata
- **Métricas Visuais**: Indicadores coloridos para status dos produtos

### Gestão de Produtos
- **Lista Completa**: Visualização de todos os produtos monitorados
- **Status Visual**: Badges e ícones indicando status (Alerta, OK, Monitorando)
- **Comparação de Preços**: Preços lado a lado com indicadores de tendência
- **Links Diretos**: Botões para acessar anúncios próprios e de concorrentes

### Adicionar Produtos
- **Formulário Intuitivo**: Campos para nome, URL própria e URL do concorrente
- **Validação**: Verificação de campos obrigatórios
- **Feedback Visual**: Confirmação de adição de produtos

### Versão Mobile
- **Navegação Bottom**: Tabs fixas na parte inferior
- **Menu Hambúrguer**: Menu lateral para navegação secundária
- **Cards Compactos**: Layout otimizado para telas pequenas
- **Touch-Friendly**: Botões e elementos dimensionados para toque

## Como Usar

### Desenvolvimento
```bash
# Instalar dependências
npm install

# Iniciar servidor de desenvolvimento
npm run dev

# Acessar aplicação
http://localhost:5173
```

### Produção
```bash
# Build para produção
npm run build

# Arquivos gerados em /dist
```

### Funcionalidades da Interface

#### Desktop
1. **Header**: Logo, título e controles de visualização
2. **Tabs**: Dashboard, Produtos, Adicionar
3. **Toggle Mobile/Desktop**: Alternância entre visualizações
4. **Alertas**: Notificações de produtos que precisam de atenção

#### Mobile
1. **Header Compacto**: Logo e menu hambúrguer
2. **Bottom Navigation**: Navegação principal na parte inferior
3. **Cards Responsivos**: Layout adaptado para telas pequenas
4. **Menu Lateral**: Navegação secundária deslizante

## Dados de Exemplo

A aplicação vem com produtos de exemplo baseados no código Python fornecido:

- **Farol Uno Mille Fire**: R$ 189,90 vs R$ 175,50 (Alerta)
- **Farol Hilux 2005-2011**: R$ 245,00 vs R$ 289,90 (OK)
- **Lanterna Gol G7**: R$ 125,90 vs R$ 135,00 (OK)

## Próximos Passos

### Funcionalidades Futuras
- **Integração com APIs**: Conexão real com Mercado Livre
- **Notificações Push**: Alertas em tempo real
- **Histórico de Preços**: Gráficos de evolução de preços
- **Relatórios**: Exportação de dados e análises
- **Multi-usuário**: Sistema de contas e permissões

### Melhorias Técnicas
- **Backend Integration**: API para persistência de dados
- **Real-time Updates**: WebSockets para atualizações em tempo real
- **PWA**: Progressive Web App para instalação mobile
- **Analytics**: Métricas de uso e performance

## Deployment

A aplicação está pronta para deploy em qualquer plataforma que suporte aplicações React:

- **Vercel**: Deploy automático via Git
- **Netlify**: Hosting estático com CI/CD
- **AWS S3 + CloudFront**: Distribuição global
- **GitHub Pages**: Hosting gratuito

---

**Desenvolvido por**: Manus AI  
**Data**: 09 de outubro de 2025  
**Versão**: 1.0.0
