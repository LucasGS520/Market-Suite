/// <reference types="vite/client" />

// Re-exporta constantes compartilhadas do pacote `shared`
export { COOKIE_NAME, ONE_YEAR_MS } from "@shared/const";

/**
 * Título da aplicação.
 * - Pode ser customizado via variável de ambiente VITE_APP_TITLE.
 * - Valor padrão: "App".
 */
export const APP_TITLE = import.meta.env.VITE_APP_TITLE || "App";

/**
 * URL do logo da aplicação.
 * - Pode ser customizado via variável de ambiente VITE_APP_LOGO.
 * - Valor padrão: imagem placeholder pública.
 */
export const APP_LOGO =
  import.meta.env.VITE_APP_LOGO ||
  "https://placehold.co/128x128/E1E7EF/1F2937?text=App";

/**
 * Gera a URL de login em tempo de execução para que o redirect URI
 * reflita a origem (origin) atual da aplicação.
 *
 * Observações:
 * - O redirectUri usa window.location.origin para suportar ambientes
 *   de desenvolvimento e produção sem configuração adicional.
 * - O parâmetro `state` é o redirectUri codificado em base64 (btoa),
 *   utilizado pelo fluxo OAuth para correlacionar a resposta.
 *
 * Retorno:
 * - string: URL completa para iniciar o fluxo de autenticação no portal OAuth.
 */
export const getLoginUrl = () => {
  // URL base do portal OAuth (deve vir de variáveis de ambiente)
  const oauthPortalUrl = import.meta.env.VITE_OAUTH_PORTAL_URL;
  // Identificador da aplicação registrado no portal OAuth
  const appId = import.meta.env.VITE_APP_ID;
  // Garante que as variáveis obrigatórias existam antes de montar a URL
  if (!oauthPortalUrl || !appId) {
    throw new Error(
      "Configuração incompleta: defina VITE_OAUTH_PORTAL_URL e VITE_APP_ID para gerar o login.",
    );
  }
  // Redirect URI construído a partir da origem atual do navegador
  const redirectUri = `${window.location.origin}/api/oauth/callback`;
  // Estado usado para correlacionar requisição/resposta (simplesmente codifica o redirectUri)
  const state = btoa(redirectUri);

  const url = new URL(`${oauthPortalUrl}/app-auth`);
  url.searchParams.set("appId", appId);
  url.searchParams.set("redirectUri", redirectUri);
  url.searchParams.set("state", state);
  url.searchParams.set("type", "signIn");

  return url.toString();
};
