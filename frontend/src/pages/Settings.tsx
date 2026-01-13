/**
 * Página de configurações do usuário do frontend.
 */

import React, { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
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
    description: 'Dados pessoais, email e telefone',
  },
  {
    id: 'notifications',
    label: 'Notificações',
    description: 'Canais habilitados e alertas.',
  },
  {
    id: 'language',
    label: 'Idioma e Acessibilidade',
    description: 'Preferências visuais, de idioma e acessibilidade',
    visualOnly: true,
  },
  {
    id: 'billing',
    label: 'Pagamento e Assinaturas',
    description: 'Planos e histórico de cobrança',
    visualOnly: true,
  },
  {
    id: 'help',
    label: 'Ajuda e Suporte',
    description: 'Central de suporte e artigos.',
    visualOnly: true,
  },
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
