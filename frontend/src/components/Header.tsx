/**
 * Componente de cabeçalho principal da aplicação (Market Alert).
 * Este arquivo contém o AppBar com navegação principal (Desktop e Mobile) e o menu de perfil do usuário.
 */

import React, { useState } from 'react';
import { useNavigate, Link as RouterLink } from 'react-router-dom';
import {
  AppBar,
  Toolbar,
  Typography,
  Button,
  IconButton,
  Menu,
  MenuItem,
  Box,
  useTheme,
  useMediaQuery,
} from '@mui/material';
import {
  Dashboard as DashboardIcon,
  Inventory as InventoryIcon,
  CompareArrows as CompareIcon,
  Notifications as NotificationsIcon,
  AccountCircle,
  Menu as MenuIcon,
} from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';

/**
 * Header
 * Componente funcional que exibe a barra de navegação superior.
 *
 * - Mostra links principais (Dashboard, Produtos, Comparação, Alertas).
 * - Em dispositivos móveis apresenta um menu "hamburger".
 * - Exibe menu de perfil com email do usuário, link para configurações e logout.
 *
 * Retorna JSX do AppBar com comportamento responsivo.
 */
const Header: React.FC = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  // Obtém tema e detector de tamanho de tela para alternar entre Desktop/Mobile.
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  
  // Estado do menu de perfil (desktop) e menu móvel (hamburger).
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [mobileMenuAnchor, setMobileMenuAnchor] = useState<null | HTMLElement>(null);

  /**
   * handleProfileMenuOpen
   * Abre o menu de perfil (desktop) posicionando-o no elemento clicado.
   */
  const handleProfileMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  /**
   * handleMobileMenuOpen
   * Abre o menu móvel (hamburger) posicionando-o no elemento clicado.
   */
  const handleMobileMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setMobileMenuAnchor(event.currentTarget);
  };

  /**
   * handleMenuClose
   * Fecha ambos menus (perfil e móvel). Útil para reutilizar ao navegar/efetuar logout.
   */
  const handleMenuClose = () => {
    setAnchorEl(null);
    setMobileMenuAnchor(null);
  };

  /**
   * handleLogout
   * Realiza logout assíncrono via contexto de autenticação, fecha menus e redireciona para a tela de login.
   */
  const handleLogout = async () => {
    await logout();
    handleMenuClose();
    navigate('/login');
  };

  // Itens exibidos no menu principal (usar ícones e rotas consistentes com o frontend).
  const menuItems = [
    { label: 'Dashboard', path: '/dashboard', icon: <DashboardIcon /> },
    { label: 'Produtos', path: '/products', icon: <InventoryIcon /> },
    { label: 'Comparação', path: '/compare', icon: <CompareIcon /> },
    { label: 'Alertas', path: '/alerts', icon: <NotificationsIcon /> },
  ];

  return (
    <AppBar position="sticky" elevation={1}>
      <Toolbar>
        {/* Logo / título que navega para o dashboard */}
        <Typography
          variant="h6"
          component={RouterLink}
          to="/dashboard"
          sx={{
            flexGrow: 0,
            textDecoration: 'none',
            color: 'inherit',
            fontWeight: 'bold',
            mr: 4,
          }}
        >
          Market Alert
        </Typography>

        {/* Menu Desktop: botões visíveis quando não é dispositivo móvel */}
        {!isMobile && (
          <Box sx={{ flexGrow: 1, display: 'flex', gap: 1 }}>
            {menuItems.map((item) => (
              <Button
                key={item.path}
                component={RouterLink}
                to={item.path}
                color="inherit"
                startIcon={item.icon}
              >
                {item.label}
              </Button>
            ))}
          </Box>
        )}

        {/* Menu Mobile: ícone de menu que abre um Menu com MenuItems */}
        {isMobile && (
          <>
            {/* Espaço flexível para empurrar o botão do menu para a direita */}
            <Box sx={{ flexGrow: 1 }} />
            <IconButton
              color="inherit"
              onClick={handleMobileMenuOpen}
              edge="start"
            >
              <MenuIcon />
            </IconButton>
            <Menu
              anchorEl={mobileMenuAnchor}
              open={Boolean(mobileMenuAnchor)}
              onClose={handleMenuClose}
            >
              {menuItems.map((item) => (
                <MenuItem
                  key={item.path}
                  onClick={() => {
                    navigate(item.path);
                    handleMenuClose();
                  }}
                >
                  {item.icon}
                  <Typography sx={{ ml: 1 }}>{item.label}</Typography>
                </MenuItem>
              ))}
            </Menu>
          </>
        )}

        {/* Perfil do Usuário: mostra email, configurações e botão de sair */}
        {!isMobile && <Box sx={{ flexGrow: 1 }} />}
        <IconButton
          color="inherit"
          onClick={handleProfileMenuOpen}
          edge="end"
        >
          <AccountCircle />
        </IconButton>
        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={handleMenuClose}
        >
          {/* Email do usuário exibido como item desabilitado */}
          <MenuItem disabled>
            <Typography variant="body2">{user?.email}</Typography>
          </MenuItem>

          {/* Link para configurações do usuário */}
          <MenuItem
            onClick={() => {
              navigate('/settings');
              handleMenuClose();
            }}
          >
            Configurações
          </MenuItem>

          {/* Ação de logout */}
          <MenuItem onClick={handleLogout}>Sair</MenuItem>
        </Menu>
      </Toolbar>
    </AppBar>
  );
};

export default Header;
