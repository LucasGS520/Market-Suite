/**
 * Seção placeholder para áreas em desenolvimento
 */

import React  from "react";
import { Alert, Card, CardContent, Stack, Typography } from '@mui/material';

interface PlaceholderSectionProps {
  title: string;
  description: string;
}

/**
 * PlaceholderSection
 * Exibe mensagem de aviso para seções ainda não implementadas
 */
const PlaceholderSection: React.FC<PlaceholderSectionProps> = ({ title, description }) => {
  return (
    <Stack spacing={3}>
      <Alert severity="warning">Esta seção está em desenolvimento.</Alert>
      <Card elevation={2}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            {title}
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
