/**
 * Botão reutilizável para reenvio com cooldown
 * Controla o tempo de espera entre emvios e exibe contador visual
 */

import React, { useEffect, useState } from 'react';
import { Button } from '@mui/material';

interface ResendButtonProps {
  label: string;
  onResend: () => Promise<void> | void;
  cooldownSeconds?: number;
  disabled?: boolean;
}

const ResendButton: React.FC<ResendButtonProps> = ({
  label,
  onResend,
  cooldownSeconds = 60,
  disabled = false,
}) => {
  const [remaining, setRemaining] = useState(0);
  const isCoolingDown = remaining > 0;

  useEffect(() => {
    if (!isCoolingDown) {
      return;
    }
    const interval = window.setInterval(() => {
      setRemaining((current) => Math.max(current - 1, 0));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [isCoolingDown]);

  const handleClick = async () => {
    try {
      await onResend();
      setRemaining(cooldownSeconds);
    } catch {
      // Mantém o botão habilitado quando o reenvio falha.
    }
  };

  return (
    <Button
      variant="outlined"
      onClick={handleClick}
      disabled={disabled || isCoolingDown}
      fullWidth
    >
      {isCoolingDown ? `${label} (${remaining}s)` : label}
    </Button>
  );
};

export default ResendButton;
