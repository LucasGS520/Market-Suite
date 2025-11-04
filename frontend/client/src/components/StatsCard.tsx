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
 * Componente de card de estatísticas
 */
export const StatsCard: React.FC<StatsCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  variant = 'default',
}) => {
  const variantStyles = {
    default: 'bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800',
    alert: 'bg-red-50 dark:bg-red-950 border-red-200 dark:border-red-800',
    success: 'bg-green-50 dark:bg-green-950 border-green-200 dark:border-green-800',
    warning: 'bg-orange-50 dark:bg-orange-950 border-orange-200 dark:border-orange-800',
  };

  const iconStyles = {
    default: 'text-blue-600 dark:text-blue-400',
    alert: 'text-red-600 dark:text-red-400',
    success: 'text-green-600 dark:text-green-400',
    warning: 'text-orange-600 dark:text-orange-400',
  };

  return (
    <Card className={`${variantStyles[variant]} border`}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <Icon className={`h-4 w-4 ${iconStyles[variant]}`} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
      </CardContent>
    </Card>
  );
};
