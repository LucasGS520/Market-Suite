// Página 404 — Componente NotFound
// Exibe uma tela amigável quando a rota não é encontrada.

import { Button } from "@/components/ui/button/button";
import { Card, CardContent } from "@/components/ui/data-display/card";
import { AlertCircle, Home } from "lucide-react";
import { useLocation } from "wouter";

/**
 * NotFound
 *
 * Componente de página 404 simples e auto-contido.
 * - Não recebe props.
 * - Usa `useLocation` do Wouter para navegar de volta à home.
 * - Estrutura baseada em Card com ícone, título, descrição e ação.
 */
export default function NotFound() {
  // useLocation retorna [location, setLocation]; apenas precisamos do setter.
  const [, setLocation] = useLocation();

  // Função acionada ao clicar em "Go Home" — redireciona para "/".
  const handleGoHome = () => {
    setLocation("/");
  };

  return (
    // Container centralizado com gradiente de fundo
    <div className="min-h-screen w-full flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100">
      {/* Cartão principal com leve transparência e blur */}
      <Card className="w-full max-w-lg mx-4 shadow-lg border-0 bg-white/80 backdrop-blur-sm">
        <CardContent className="pt-8 pb-8 text-center">
          {/* Área do ícone (alerta) */}
          <div className="flex justify-center mb-6">
            <div className="relative">
              {/* Fundo pulsante para dar ênfase */}
              <div className="absolute inset-0 bg-red-100 rounded-full animate-pulse" />
              <AlertCircle className="relative h-16 w-16 text-red-500" />
            </div>
          </div>

          {/* Código de erro em destaque */}
          <h1 className="text-4xl font-bold text-slate-900 mb-2">404</h1>

          {/* Título explicativo */}
          <h2 className="text-xl font-semibold text-slate-700 mb-4">
            Página não encontrada
          </h2>

          {/* Mensagem adicional explicativa */}
          <p className="text-slate-600 mb-8 leading-relaxed">
            Desculpe, a página que você está procurando não existe.
            <br />
            Ela pode ter sido movida ou removida.
          </p>

          {/* Ações (botões) — atualmente apenas voltar para home */}
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Button
              onClick={handleGoHome}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2.5 rounded-lg transition-all duration-200 shadow-md hover:shadow-lg"
            >
              <Home className="w-4 h-4 mr-2" />
              Voltar para Início
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
