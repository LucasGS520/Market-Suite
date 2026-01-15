/**
 * Componente utilitário para exibir textos truncados com reticências e tooltip.
 *
 * Permite definir quantidade de linhas, largura máxima e estilização adicional
 * mantendo acessibilidade via atributo title. Pode ser reutilizado em tabelas e
 * cartões para evitar que textos longos quebrem o layout.
 */

import React from 'react';
import { Tooltip, Typography, Box, type TypographyProps, type SxProps, type Theme } from '@mui/material';

export interface TruncatedTextProps extends TypographyProps {
  text: string;
  lines?: number;
  maxWidth?: number | string;
  tooltip?: boolean;
}

const TruncatedText: React.FC<TruncatedTextProps> = ({
  text,
  lines = 1,
  maxWidth,
  tooltip = false,
  sx,
  ...typographyProps
}) => {
  const clampMultipleLines = lines > 1;

  const sharedSx = {
    maxWidth,
    WebkitLineClamp: clampMultipleLines ? lines : undefined,
    WebkitBoxOrient: clampMultipleLines ? 'vertical' : undefined,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: clampMultipleLines ? 'normal' : 'nowrap',
    ...sx,
  };

  // Mantém um wrapper estável para que o Tooltip não altere o layout no hover.
  // O Box concentra a lógica de truncamento e preserva as dimensões.
  // Resolve a largura efetiva do wrapper: se `maxWidth` foi fornecido use ele,
  // caso contrário ocupe 100% do espaço do pai. Para single-line usamos
  // `display: block` + `width: 100%` para garantir que o text-overflow
  // se aplique corretamente e a URL não ultrapasse o card.
  const resolvedWidth = maxWidth ?? '100%';

  const wrapperSx: SxProps<Theme> = {
    ...sharedSx,
    display: clampMultipleLines ? '-webkit-box' : 'block',
    width: typeof resolvedWidth === 'number' ? `${resolvedWidth}px` : resolvedWidth,
    boxSizing: 'border-box',
  } as SxProps<Theme>;

  // O atributo tittle aó é aplicado quando não há tooltip, evitando o warning do MUI
  const inner = (
    <Box component="span" sx={wrapperSx} {...(!tooltip ? { title: text } : {})}>
      <Typography {...typographyProps} noWrap={!clampMultipleLines} sx={{ display: 'block' }}>
        {text}
      </Typography>
    </Box>
  );

  if (!tooltip) return inner;

  return (
    <Tooltip title={text} enterDelay={300} leaveDelay={50}>
      {inner}
    </Tooltip>
  );
};

export default TruncatedText;
