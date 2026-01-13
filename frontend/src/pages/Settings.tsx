/**
 * Página de configurações do usuário do frontend.
 */

import React, { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import LanguageIcon from '@mui/icons-material/Language';
import NotificationsNoneIcon from '@mui/icons-material/NotificationsNone';
import PaymentIcon from '@mui/icons-material/Payment';
import PersonOutlineIcon from '@mui/icons-material/PersonOutline';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import SettingsLayout from '../components/settings/SettingsLayout';
import SettingsMenu, { SettingsMenuItem } from '../components/settings/SettingsMenu';
import ProfileSection from './settings/ProfileSection';
import NotificationsSection from './settings/NotificationsSection';
import LanguageAccessibilitySection from './settings/LanguageAccessibilitySection';
import PlaceholderSection from './settings/PlaceholderSection';

const SETTINGS_SECTIONS: SettingsMenuItem[] = [
  {
    id: 'profile',
    label: 'Perfil',
    icon: <PersonOutlineIcon fontSize="small" />,
  },
  {
    id: 'notifications',
    label: 'Notificações',
    icon: <NotificationsNoneIcon fontSize="small" />,
  },
  {
    id: 'language',
    label: 'Idioma & Acessibilidade',
    icon: <LanguageIcon fontSize="small" />,
    visualOnly: true,
  },
  {
    id: 'billing',
    label: 'Pagamento & Assinaturas',
    icon: <PaymentIcon fontSize="small" />,
    visualOnly: true,
  },
  {
    id: 'help',
    label: 'Ajuda',
    icon: <HelpOutlineIcon fontSize="small" />,
    visualOnly: true,
  },
  {
    id: 'about',
    label: 'Sobre',
    icon: <InfoOutlinedIcon fontSize="small" />,
    visualOnly: true,
  }
];

/**
 * Componente de página de Configurações do usuário.
 *
 * Organiza a navegação entre seções de configurações sem recarregar a página.
 */
const Settings: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeSection = searchParams.get('section') ?? 'profile';

  const sectionContent = useMemo(() => {
    switch (activeSection) {
      case 'notifications':
        return <NotificationsSection />;
      case 'language':
        return <LanguageAccessibilitySection />;
      case 'billing':
        return (
          <PlaceholderSection
            title="Pagamentos & Assinaturas"
            description="Gerencie planos, métodos de pagamento e recibos em breve."
          />
        );
      case 'help':
        return (
          <PlaceholderSection
            title="Ajuda"
            description="Conteúdo de suporte e canais de atendimento estarão disponíveis em breve."
          />
        );
      case 'about':
        return (
          <PlaceholderSection
            title="Sobre"
            description="Informações institucionais e versão do produto estarão aqui."
          />
        );
      case 'profile':
      default:
        return <ProfileSection />;
    }
  }, [activeSection]);

  const handleSelect = (id: string) => {
    setSearchParams({ section: id });
  };

  return (
    <SettingsLayout
      title="Configurações"
      subtitle="Gerencie preferências sincronizadas e ajustes visuais locais."
      menu={<SettingsMenu items={SETTINGS_SECTIONS} activeId={activeSection} onSelect={handleSelect} />}
    >
      {sectionContent}
    </SettingsLayout>            
  );
};

export default Settings;
