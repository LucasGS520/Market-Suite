/**
 * Configuração do Tailwind CSS para o frontend do projeto Market Suite.
 */

/** @type {import('tailwindcss').Config} */
export default {
  // Onde o Tailwind vai escanear por classes utilitárias usadas no projeto.
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],

  // Personalizações de tema (cores, fontes, espaçamentos, etc).
  // Utilize `extend` para adicionar ou sobrescrever valores mantendo o padrão do Tailwind.
  theme: {
    extend: {
      // Paleta customizada para o design system:
      colors: {
        primary: {
          50: '#fff6ed',
          100: '#ffe8cc',
          200: '#ffd0a1',
          300: '#ffb776',
          400: '#ff9e3a',
          500: '#fb8c00', // cor primária (laranja)
          600: '#ef6c00',
          700: '#e65100',
          800: '#c43f00',
          900: '#9b2b00',
        },
        secondary: {
          50: '#fffdea',
          100: '#fff8cc',
          200: '#fff1a8',
          300: '#ffea84',
          400: '#ffe65a',
          500: '#fdd835', // cor secundária (amarelo)
          600: '#f6cf2b',
          700: '#f0c022',
          800: '#e0a800',
          900: '#b38200',
        },
      },
      // Adicione outras customizações específicas do design system aqui.
    },
  },

  // Plugins oficiais ou de terceiros podem ser adicionados aqui
  // Exemplo: require('@tailwindcss/forms'), require('@tailwindcss/typography')
  plugins: [],
}
