/**
 * Componente responsável por exibir ações em massa sobre concorrentes.
 *
 * - Mostra o total selecionado e disponibiliza botões para pausar, retomar ou remover.
 * - É reusado na página de concorrentes para manter consistência visual.
 */

import React from 'react';
import { Loader2, Pause, Play, Trash2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/overlay/alert-dialog';

/**
 * Propriedades aceitas pela barra de ações em massa.
 */
export interface BulkActionsBarProps {
  selectedCount: number;
  totalCount: number;
  onPause: () => Promise<void>;
  onResume: () => Promise<void>;
  onRemove: () => Promise<void>;
  onClear: () => void;
  isProcessing: boolean;
}

/**
 * Barra de ações em massa exibida quando há concorrentes selecionados.
 */
export const BulkActionsBar: React.FC<BulkActionsBarProps> = ({
  selectedCount,
  totalCount,
  onPause,
  onResume,
  onRemove,
  onClear,
  isProcessing,
}) => (
  <Card className="border-primary/40 bg-primary/5">
    <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-sm font-medium">
          {selectedCount} de {totalCount} concorrentes selecionados
        </p>
        <p className="text-xs text-muted-foreground">Escolha uma ação para aplicar ao conjunto selecionado.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {/* Ação em massa: pausar concorrentes selecionados */}
        <Button type="button" variant="secondary" disabled={isProcessing} onClick={onPause}>
          {isProcessing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Pause className="h-4 w-4" />} Pausar
        </Button>

        {/* Ação em massa: retomar concorrentes selecionados */}
        <Button type="button" variant="secondary" disabled={isProcessing} onClick={onResume}>
          {isProcessing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Retomar
        </Button>

        {/* Ação em massa: remover concorrentes (confirmação) */}
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button type="button" variant="destructive" disabled={isProcessing}>
              {isProcessing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />} Remover
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Remover concorrentes selecionados</AlertDialogTitle>
              <AlertDialogDescription>
                Esta ação removerá {selectedCount} concorrentes e limpará seus históricos associados. Deseja prosseguir?
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction onClick={onRemove}>Remover</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Limpa seleção atual */}
        <Button type="button" variant="ghost" disabled={isProcessing} onClick={onClear}>
          Limpar seleção
        </Button>
      </div>
    </CardContent>
  </Card>
);

export default BulkActionsBar;