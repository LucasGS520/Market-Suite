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
      // Exemplo:
      // colors: {
      //   brand: {
      //     50: '#f5fbff',
      //     500: '#1e90ff',
      //   },
      // },
      //
      // Adicione customizações específicas do design system aqui.
    },
  },

  // Plugins oficiais ou de terceiros podem ser adicionados aqui
  // Exemplo: require('@tailwindcss/forms'), require('@tailwindcss/typography')
  plugins: [],
}
