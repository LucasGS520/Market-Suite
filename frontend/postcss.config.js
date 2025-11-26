/**
 * Configuração do PostCSS para o frontend.
 *
 * Este arquivo exporta o objeto de configuração do PostCSS (ESM).
 * Contém os plugins ativados para o pipeline de transformação CSS
 */
export default {
  plugins: {
    '@tailwindcss/postcss': {}, // Plugin do TailwindCSS: processa diretivas e utilitários do Tailwind.
    autoprefixer: {}, // Autoprefixer: insere prefixes CSS necessários para navegadores alvo.
  },
}
