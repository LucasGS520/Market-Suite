import apiClient from "../lib/api";

export interface ProfileResponse {
  id: string;
  name: string;
  email: string;
  phone_number?: string | null;
  email_verified: boolean;
  phone_number_verified: boolean;
}

export interface ProfileUpdatePayload {
  name?: string;
  email?: string;
  phone_number?: string | null;
}

export interface ProfileUpdateResponse {
  profile: ProfileResponse;
  email_verification_required: boolean;
  phone_verification_required: boolean;
}

export interface NotificationSettings {
  email: boolean;
  push: boolean;
  sms: boolean;
  whatsapp: boolean;
}

/**
 * Busca o perfil do usuário autenticado para a tela de configurações
 */
export const getProfile = async (): Promise<ProfileResponse> => {
  const response = await apiClient.get<ProfileResponse>('/settings/profile');
  return response.data;
};

/**
 * Atualiza o perfil do usuário autenticado
 */
export const updateProfile = async (payload: ProfileUpdatePayload): Promise<ProfileUpdateResponse> => {
  const response = await apiClient.patch<ProfileUpdateResponse>('/settings/profile', payload);
  return response.data;
};

/**
 * Busca as preferências globais de canais de notificação
 */
export const getNotificationSettings = async (): Promise<NotificationSettings> => {
  const response = await apiClient.get<NotificationSettings>('/settings/notifications');
  return response.data;
};

/**
 * Atualiza as preferências globais de canais de notificação
 */
export const updateNotificationSettings = async (
  payload: NotificationSettings
): Promise<NotificationSettings> => {
  const response = await apiClient.patch<NotificationSettings>('/settings/notifications', payload);
  return response.data;
};
