/**
 * Página de Produtos Monitorados
 *
 * Este arquivo contém a página React responsável por listar, procurar, filtrar e
 * adicionar produtos monitorados pelo usuário.
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box,
  Typography,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Card,
  CardContent,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  ToggleButton,
  ToggleButtonGroup,
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  Add as AddIcon,
  ViewList as ViewListIcon,
  ViewModule as ViewModuleIcon,
  TrendingUp as TrendingUpIcon,
} from '@mui/icons-material';
import { productsService } from '../services/productsService';
import Layout from '../components/Layout';
import { formatCurrency } from '../utils/currency';

/**
 * Componente principal da página de Produtos Monitorados.
 * - Buscar produtos monitorados com paginação, busca e filtro de status.
 * - Permitir alternância de visualização (lista / tabela).
 * - Abrir diálogo para adicionar novo produto.
 *
 * Retorna a interface de gerenciamento de produtos.
 */
const Products: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Estado da UI
  const [viewMode, setViewMode] = useState<'list' | 'table'>('list'); // modo de exibição
  const [searchQuery, setSearchQuery] = useState(''); // texto de busca
  const [statusFilter, setStatusFilter] = useState(''); // filtro por status de competitividade
  const [page] = useState(1); // página atual (para paginação)
  const [openAddDialog, setOpenAddDialog] = useState(false); // controla diálogo de adicionar produto
  const [newProductUrl, setNewProductUrl] = useState(''); // URL do novo produto
  const [newProductName, setNewProductName] = useState(''); // nome opcional do novo produto
  const [creationFeedback, setCreationFeedback] = useState<string | null>(null); // mensagem pós-criação
  const [creationError, setCreationError] = useState<string | null>(null); // erro ao criar produto

  // Query para buscar produtos monitorados. A chave depende de pagina, busca e filtro.
  const { data, isLoading, error } = useQuery({
    queryKey: ['monitoredProducts', page, searchQuery, statusFilter],
    queryFn: () =>
      productsService.getMonitoredProducts({
        page,
        per_page: viewMode === 'list' ? 5 : 100,
        query: searchQuery || undefined,
        status: statusFilter || undefined,
      }),
  });

  // Mutation para criação de produto monitorado.
  const createProductMutation = useMutation({
    mutationFn: productsService.createMonitoredProduct,
    onSuccess: () => {
      // Invalida cache para forçar refresh da lista atualizada
      queryClient.invalidateQueries({ queryKey: ['monitoredProducts'] });
      // Fecha diálogo e reseta campos do formulário
      setOpenAddDialog(false);
      setNewProductUrl('');
      setNewProductName('');
      setCreationError(null);
      // Feedback explícito para sinalizar que o backend ainda processará o scraping
      setCreationFeedback('Produto criado e scraping em andamento. Lista atualizada automaticamente.');
    },
    onError: () => {
      // Mantém mensagem amigável para orientar ajuste de URL ou reautenticação
      setCreationError('Não foi possível criar o produto. Verifique a URL e tente novamente.');
    }
  });

  /**
   * Handler para enviar criação de novo produto.
   * Valida presença de URL antes de disparar mutation.
   */
  const handleAddProduct = () => {
    if (!newProductUrl) return;
    createProductMutation.mutate({
      product_url: newProductUrl,
      name_identification: newProductName || undefined,
    });
  };

  /**
   * Retorna a cor do Chip de status com base no status de competitividade.
   * Usado para manter consistência visual com MUI.
   */
  const getStatusColor = (status?: string) => {
    switch (status) {
      case 'competitivo':
        return 'success';
      case 'atencao':
        return 'warning';
      case 'nao_competitivo':
        return 'warning';
      case 'urgente':
        return 'error';
      default:
        return 'default';
    }
  };

  /**
   * Formata o preço exibindo rótulo de coleta quando ainda não há valor disponível.
   */
  const renderPrice = (value: string | number | null) => {
    if (value === null) {
      return 'Coletando preço...';
    }

    return formatCurrency(value);
  };

  /**
   * Retorna label legível para o status de competitividade.
   */
  const getStatusLabel = (status?: string) => {
    switch (status) {
      case 'competitivo':
        return 'Competitivo';
      case 'atencao':
        return 'Atenção';
      case 'nao_competitivo':
        return 'Não Competitivo';
      case 'urgente':
        return 'Urgente';
      default:
        return 'Sem Status';
    }
  };

  return (
    <Layout>
      {/* Cabeçalho */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom>
          Produtos Monitorados
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Gerencie e visualize todos os seus produtos monitorados
        </Typography>
      </Box>

      {/* Barra de Ações */}
      <Box sx={{ mb: 3, display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setOpenAddDialog(true)}
        >
          Adicionar Produto
        </Button>

        <TextField
          size="small"
          placeholder="Buscar produtos..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          sx={{ minWidth: 200 }}
        />

        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>Status</InputLabel>
          <Select
            value={statusFilter}
            label="Status"
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <MenuItem value="">Todos</MenuItem>
            <MenuItem value="competitivo">Competitivo</MenuItem>
            <MenuItem value="atencao">Atenção</MenuItem>
            <MenuItem value="nao_competitivo">Não Competitivo</MenuItem>
            <MenuItem value="urgente">Urgente</MenuItem>
          </Select>
        </FormControl>

        {/* Espaço flexível para empurrar os botões do lado direito */}
        <Box sx={{ flexGrow: 1 }} />

        {/* Alterna entre visualização em lista e tabela */}
        <ToggleButtonGroup
          value={viewMode}
          exclusive
          onChange={(_, newMode) => newMode && setViewMode(newMode)}
          size="small"
        >
          <ToggleButton value="list">
            <ViewListIcon />
          </ToggleButton>
          <ToggleButton value="table">
            <ViewModuleIcon />
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {/* Feedback para criação de produto */}
      {creationFeedback && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {creationFeedback}
        </Alert>
      )}
      {creationError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {creationError}
        </Alert>
      )}

      {/* Conteúdo */}
      {isLoading ? (
        // Estado de carregamento
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress />
        </Box>
      ) : error ? (
        // Estado de erro ao buscar produtos
        <Alert severity="error">Erro ao carregar produtos. Tente novamente.</Alert>
      ) : data && data.items.length > 0 ? (
        viewMode === 'list' ? (
          // Modo Lista - exibe cartões por produto
          <Grid container spacing={3}>
            {data.items.map((product) => (
              <Grid item xs={12} key={product.id}>
                <Card elevation={2}>
                  <CardContent>
                    <Box display="flex" gap={2}>
                      {product.thumbnail && (
                        <Box
                          component="img"
                          src={product.thumbnail}
                          alt={product.name}
                          sx={{
                            width: 100,
                            height: 100,
                            objectFit: 'cover',
                            borderRadius: 1,
                          }}
                        />
                      )}
                      <Box flex={1}>
                        <Box display="flex" justifyContent="space-between" alignItems="start">
                          <Box>
                            <Typography variant="h6">{product.name}</Typography>
                            <Typography variant="body2" color="text.secondary">
                              Origem: {new URL(product.url).hostname}
                            </Typography>
                          </Box>
                          <Chip
                            label={getStatusLabel(product.competitiveness_status)}
                            color={getStatusColor(product.competitiveness_status)}
                            size="small"
                          />
                        </Box>

                        {/* Informações de preço resumidas */}
                        <Grid container spacing={2} sx={{ mt: 2 }}>
                          <Grid item xs={4}>
                          <Typography variant="body2" color="text.secondary">
                              MEU PREÇO
                            </Typography>
                            <Typography variant="h5" color="primary">
                              {renderPrice(product.current_price)}
                            </Typography>
                          </Grid>
                          <Grid item xs={4}>
                            <Typography variant="body2" color="text.secondary">
                              MENOR CONCORRENTE
                            </Typography>
                            <Typography variant="h5" color="success.main">
                              R$ 0,00
                            </Typography>
                          </Grid>
                          <Grid item xs={4}>
                            <Typography variant="body2" color="text.secondary">
                              DIFERENÇA
                            </Typography>
                            <Box display="flex" alignItems="center" gap={0.5}>
                              <TrendingUpIcon color="error" />
                              <Typography variant="h5" color="error">
                                R$ 0,00
                              </Typography>
                            </Box>
                          </Grid>
                        </Grid>

                        {/* Rodapé do cartão com ações */}
                        <Box display="flex" justifyContent="space-between" alignItems="center" mt={2}>
                          <Typography variant="body2" color="text.secondary">
                            Ranking #1 de 1 | 0 concorrentes
                          </Typography>
                          <Button
                            variant="contained"
                            size="small"
                            onClick={() => navigate(`/product/${product.id}`)}
                          >
                            Ver Detalhes
                          </Button>
                        </Box>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        ) : (
          // Modo Tabela - exibe produtos em linhas
          <TableContainer component={Paper} elevation={2}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Produto</TableCell>
                  <TableCell align="right">Meu Preço</TableCell>
                  <TableCell align="right">Menor Concorrente</TableCell>
                  <TableCell align="right">Diferença</TableCell>
                  <TableCell align="center">Concorrentes</TableCell>
                  <TableCell align="center">Ranking</TableCell>
                  <TableCell align="center">Status</TableCell>
                  <TableCell align="center">Ações</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.items.map((product) => (
                  <TableRow key={product.id} hover>
                    <TableCell>
                      <Box display="flex" alignItems="center" gap={1}>
                        {product.thumbnail && (
                          <Box
                            component="img"
                            src={product.thumbnail}
                            alt={product.name}
                            sx={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 1 }}
                          />
                        )}
                        <Typography variant="body2">{product.name}</Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      {renderPrice(product.current_price)}
                    </TableCell>
                    <TableCell align="right">R$ 0,00</TableCell>
                    <TableCell align="right">
                      <Typography color="error">R$ 0,00</Typography>
                    </TableCell>
                    <TableCell align="center">0</TableCell>
                    <TableCell align="center">#1 de 1</TableCell>
                    <TableCell align="center">
                      <Chip
                        label={getStatusLabel(product.competitiveness_status)}
                        color={getStatusColor(product.competitiveness_status)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Button
                        variant="outlined"
                        size="small"
                        onClick={() => navigate(`/product/${product.id}`)}
                      >
                        Ver
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )
      ) : (
        // Estado vazio - sem produtos encontrados
        <Alert severity="info">
          Nenhum produto encontrado. Adicione produtos para começar a monitorar.
        </Alert>
      )}

      {/* Dialog de Adicionar Produto */}
      <Dialog open={openAddDialog} onClose={() => setOpenAddDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Adicionar Produto Monitorado</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="URL do Produto"
            type="url"
            fullWidth
            required
            value={newProductUrl}
            onChange={(e) => setNewProductUrl(e.target.value)}
            placeholder="https://exemplo.com/produto"
          />
          <TextField
            margin="dense"
            label="Nome de Identificação (opcional)"
            type="text"
            fullWidth
            value={newProductName}
            onChange={(e) => setNewProductName(e.target.value)}
            placeholder="Ex: Monitor Gamer 27''"
          />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            O produto será processado de forma assíncrona. Aguarde alguns instantes para que apareça na lista.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenAddDialog(false)}>Cancelar</Button>
          <Button
            onClick={handleAddProduct}
            variant="contained"
            disabled={!newProductUrl || createProductMutation.isPending}
          >
            {createProductMutation.isPending ? <CircularProgress size={24} /> : 'Adicionar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Layout>
  );
};

export default Products;
