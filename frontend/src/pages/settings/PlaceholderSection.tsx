/**
 * Seção placeholder para áreas em desenvolvimento
 */

import React from 'react';
import { Card, CardContent, Stack, Typography } from '@mui/material';

interface PlaceholderSectionProps {
  title: string;
  description: string;
}

/**
 * PlaceholderSection
 * Exibe mensagem neutra para seções ainda não implementadas
 */
const PlaceholderSection: React.FC<PlaceholderSectionProps> = ({ title, description }) => {
  return (
    <Stack spacing={3}>
      <Card elevation={2}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            {title}
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
            Seção em desenvolvimento!!
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {description}
          </Typography>
        </CardContent>
      </Card>
    </Stack>
  );
};

export default PlaceholderSection;
