import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { LucideIcon } from 'lucide-react';

interface StatsCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  variant?: 'default' | 'alert' | 'success' | 'warning';
}

/**
 * Componente de card de estatísticas.
 *
 * Exibe um título, valor principal, um subtítulo opcional e um ícone.
 * Recebe um "variant" para alterar estilos de fundo/borda/ícone conforme o contexto.
 *
 * Props:
 * - title: título do card
 * - value: valor em destaque (string ou número)
 * - subtitle: texto auxiliar opcional
 * - icon: componente de ícone (lucide-react)
 * - variant: variação visual do card (default | alert | success | warning)
 */
export const StatsCard: React.FC<StatsCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  variant = 'default',
}) => {
  // Map de classes CSS por variação do componente.
  // Mantém as combinações de cores para modo claro/escuro e facilita futuras alterações de tema.
  const variantStyles: Record<NonNullable<StatsCardProps['variant']>, string> = {
    default: 'bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800',
    alert: 'bg-red-50 dark:bg-red-950 border-red-200 dark:border-red-800',
    success: 'bg-green-50 dark:bg-green-950 border-green-200 dark:border-green-800',
    warning: 'bg-orange-50 dark:bg-orange-950 border-orange-200 dark:border-orange-800',
  };

  // Cores aplicadas ao ícone conforme a variação.
  // Separar estilo de ícone facilita consistência visual entre diferentes tipos de cards.
  const iconStyles: Record<NonNullable<StatsCardProps['variant']>, string> = {
    default: 'text-blue-600 dark:text-blue-400',
    alert: 'text-red-600 dark:text-red-400',
    success: 'text-green-600 dark:text-green-400',
    warning: 'text-orange-600 dark:text-orange-400',
  };

  return (
    // Card principal com borda e background definidos pela variação.
    <Card className={`${variantStyles[variant]} border`}>
      {/* Cabeçalho: título e ícone alinhados */}
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        {/* Ícone recebido via prop; aplica classes de cor conforme a variação */}
        <Icon className={`h-4 w-4 ${iconStyles[variant]}`} />
      </CardHeader>

      {/* Conteúdo: valor em destaque e subtítulo opcional */}
      <CardContent>
        {/* Valor principal do card */}
        <div className="text-2xl font-bold">{value}</div>

        {/* Subtítulo exibido apenas se fornecido */}
        {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
      </CardContent>
    </Card>
  );
};
