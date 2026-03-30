/**
 * Componente de cabeçalho principal da aplicação (Market Suite).
 * AppBar com navegação principal (Desktop e Mobile) e menu de perfil do usuário.
 */

import React, { useState } from 'react';
import { useNavigate, useLocation, Link as RouterLink } from 'react-router-dom';
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
import { useAuth } from '../hooks/useAuth';

const Header: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();

  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [mobileMenuAnchor, setMobileMenuAnchor] = useState<null | HTMLElement>(null);

  const handleProfileMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMobileMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setMobileMenuAnchor(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
    setMobileMenuAnchor(null);
  };

  const handleLogout = async () => {
    await logout();
    handleMenuClose();
    navigate('/login');
  };

  const menuItems = [
    { label: 'Dashboard', path: '/dashboard', icon: <DashboardIcon fontSize="small" /> },
    { label: 'Produtos', path: '/products', icon: <InventoryIcon fontSize="small" /> },
    { label: 'Comparação', path: '/compare', icon: <CompareIcon fontSize="small" /> },
    { label: 'Alertas', path: '/alerts', icon: <NotificationsIcon fontSize="small" /> },
  ];

  // Estilos compartilhados para menus dropdown (perfil e mobile)
  const menuPaperSx = {
    backgroundColor: 'var(--color-surface-popover)',
    border: '1px solid var(--color-border-contextual)',
    boxShadow: 'var(--shadow-contextual)',
    borderRadius: 'var(--radius-lg)',
    mt: 0.75,
    '& .MuiMenuItem-root': {
      fontSize: '0.875rem',
      color: 'var(--color-text-secondary)',
      borderRadius: 'var(--radius-md)',
      mx: 0.5,
      my: 0.25,
      transition: `background-color var(--motion-fast) var(--motion-easing), color var(--motion-fast) var(--motion-easing)`,
      '&:hover': {
        backgroundColor: 'var(--color-surface-hover)',
        color: 'var(--color-text-primary)',
      },
      '&.Mui-disabled': {
        opacity: 1,
        color: 'var(--color-text-muted)',
      },
    },
  };

  return (
    <AppBar
      position="sticky"
      elevation={0}
      sx={{
        backgroundColor: 'var(--color-bg-sidebar)',
        borderBottom: '1px solid var(--color-border-default)',
        backdropFilter: 'blur(8px)',
      }}
    >
      <Toolbar sx={{ gap: 1 }}>
        {/* Logo */}
        <Typography
          variant="h6"
          component={RouterLink}
          to="/dashboard"
          sx={{
            flexGrow: 0,
            textDecoration: 'none',
            display: 'inline-block',
            color: 'transparent',
            backgroundImage: 'linear-gradient(90deg, var(--color-accent-primary), var(--color-accent-secondary))',
            backgroundClip: 'text',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            fontWeight: 700,
            fontSize: '1.125rem',
            letterSpacing: '-0.02em',
            mr: 3,
          }}
        >
          Market Suite
        </Typography>

        {/* Navegação Desktop */}
        {!isMobile && (
          <Box sx={{ flexGrow: 1, display: 'flex', gap: 0.5 }}>
            {menuItems.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <Button
                  key={item.path}
                  component={RouterLink}
                  to={item.path}
                  startIcon={item.icon}
                  sx={{
                    color: isActive ? 'var(--color-accent-primary)' : 'var(--color-text-muted)',
                    backgroundColor: isActive ? 'var(--color-surface-active)' : 'transparent',
                    borderRadius: 'var(--radius-md)',
                    px: 1.5,
                    py: 0.75,
                    fontSize: '0.875rem',
                    fontWeight: isActive ? 600 : 400,
                    textTransform: 'none',
                    transition: `color var(--motion-fast) var(--motion-easing), background-color var(--motion-fast) var(--motion-easing)`,
                    '&:hover': {
                      color: 'var(--color-text-primary)',
                      backgroundColor: 'var(--color-surface-hover)',
                    },
                  }}
                >
                  {item.label}
                </Button>
              );
            })}
          </Box>
        )}

        {/* Espaço flex para empurrar ações para a direita em mobile */}
        {isMobile && <Box sx={{ flexGrow: 1 }} />}

        {/* Menu Mobile (hamburger) */}
        {isMobile && (
          <>
            <IconButton
              onClick={handleMobileMenuOpen}
              edge="start"
              aria-label="Abrir menu de navegação"
              aria-expanded={Boolean(mobileMenuAnchor)}
              aria-haspopup="true"
              sx={{
                color: 'var(--color-text-muted)',
                '&:hover': {
                  color: 'var(--color-text-primary)',
                  backgroundColor: 'var(--color-surface-hover)',
                },
              }}
            >
              <MenuIcon />
            </IconButton>
            <Menu
              anchorEl={mobileMenuAnchor}
              open={Boolean(mobileMenuAnchor)}
              onClose={handleMenuClose}
              slotProps={{ paper: { sx: menuPaperSx } }}
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
                  <Typography sx={{ ml: 1, fontSize: '0.875rem' }}>{item.label}</Typography>
                </MenuItem>
              ))}
            </Menu>
          </>
        )}

        {/* Perfil do usuário */}
        {!isMobile && <Box sx={{ flexGrow: 1 }} />}
        <IconButton
          onClick={handleProfileMenuOpen}
          edge="end"
          aria-label="Menu do usuário"
          aria-expanded={Boolean(anchorEl)}
          aria-haspopup="true"
          sx={{
            color: 'var(--color-text-muted)',
            transition: `color var(--motion-fast) var(--motion-easing), background-color var(--motion-fast) var(--motion-easing)`,
            '&:hover': {
              color: 'var(--color-accent-primary)',
              backgroundColor: 'var(--color-surface-hover)',
            },
          }}
        >
          <AccountCircle />
        </IconButton>
        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={handleMenuClose}
          slotProps={{ paper: { sx: menuPaperSx } }}
        >
          <MenuItem disabled>
            <Typography variant="body2" sx={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
              {user?.email}
            </Typography>
          </MenuItem>
          <MenuItem
            onClick={() => {
              navigate('/settings');
              handleMenuClose();
            }}
          >
            Configurações
          </MenuItem>
          <MenuItem onClick={handleLogout}>Sair</MenuItem>
        </Menu>
      </Toolbar>
    </AppBar>
  );
};

export default Header;
