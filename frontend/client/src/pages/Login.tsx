import React, { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLocation } from 'wouter';
import { Button } from '@/components/ui/button/button';
import { Input } from '@/components/ui/inputs/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Alert, AlertDescription } from '@/components/ui/feedback/alert';
import { Loader2, AlertCircle } from 'lucide-react';
import { APP_LOGO, APP_TITLE } from '@/const';

/**
 * Componente de página de Login.
 * - Gerencia estado local de email, senha, loading e erro.
 * - Usa useAuth() para executar a ação de login.
 * - Navega para a rota raiz em caso de sucesso.
 */
export default function Login() {
  // hook de autenticação do contexto (provê função login)
  const { login } = useAuth();
  // hook de roteamento (wouter) — navigate para redirecionamento pós-login
  const [, navigate] = useLocation();

  // estados locais do formulário
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Handler do submit do formulário.
   * - Previne comportamento padrão do form.
   * - Tenta executar login e redireciona em caso de sucesso.
   * - Em caso de erro, define mensagem amigável.
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await login(email, password);
      // redireciona para a página principal após login bem sucedido
      navigate('/');
    } catch (err) {
      // mantém a mensagem do Error se disponível, caso contrário mensagem genérica em PT-BR
      setError(err instanceof Error ? err.message : 'Erro ao fazer login');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    // Container centralizado com background gradiente (modo claro/escuro)
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-orange-50 to-blue-50 dark:from-slate-950 dark:to-slate-900 p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-4 text-center">
          {/* Logo e título do app */}
          <div className="flex justify-center">
            <img src={APP_LOGO} alt={APP_TITLE} className="h-12 w-12" />
          </div>
          <CardTitle className="text-2xl">{APP_TITLE}</CardTitle>
          <CardDescription>Monitoramento Inteligente de Preços</CardDescription>
        </CardHeader>

        <CardContent>
          {/* Formulário de login */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Exibe alerta de erro quando existe mensagem */}
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* Campo de email */}
            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium">
                Email
              </label>
              <Input
                id="email"
                type="email"
                placeholder="seu@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isLoading} // desabilita input durante requisição
                required
              />
            </div>

            {/* Campo de senha */}
            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium">
                Senha
              </label>
              <Input
                id="password"
                type="password"
                placeholder="Sua senha"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading} // desabilita input durante requisição
                required
              />
            </div>

            {/* Botão de submissão com estado de loading */}
            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isLoading ? 'Entrando...' : 'Entrar'}
            </Button>
          </form>

          {/* Link / instrução para criação de conta (texto informativo) */}
          <p className="text-center text-sm text-muted-foreground mt-4">
            Não tem conta? Crie uma em nosso portal.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
