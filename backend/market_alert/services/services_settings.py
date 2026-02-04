""" Serviços de leitura e atualização da área de configurações """

from __future__ import annotations

import structlog
import phonenumbers
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session
from uuid import UUID

from market_alert.core.config_alert import settings
from market_alert.core.tokens import generate_phone_otp, generate_verification_token, token_expiry
from market_alert.crud import crud_notifications, crud_user, crud_verification
from market_alert.enums.enums_notifications import NotificationChannel
from market_alert.enums.enums_users import VerificationKind
from market_alert.models.models_users import User
from market_alert.schemas.schemas_settings import (
    NotificationSettings,
    SettingsOverviewResponse,
    SettingsProfileResponse,
    SettingsProfileUpdate,
    SettingsProfileUpdateResponse,
)
from market_alert.tasks.verification_tasks import send_email_verification, send_phone_otp


logger = structlog.get_logger("service.settings")
DEFAULT_NOTIFICATION_CHANNELS = {
    NotificationChannel.email,
    NotificationChannel.push,
    NotificationChannel.sms,
    NotificationChannel.whatsapp,
}


def _normalize_email(value: str) -> str:
    """ Normaliza email garantindo letras minúsculas """
    return value.strip().lower()

def _normalize_phone(value: str | None) -> str | None:
    """ Normaliza telefone para o formato E.164 """
    if not value:
        return None
    try:
        parsed = phonenumbers.parse(value, "BR")
    except phonenumbers.NumberParseException:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Telefone inválido")
    if not phonenumbers.is_valid_number(parsed):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Telefone inválido")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

def _resolve_phone_for_update(payload: SettingsProfileUpdate, user: User) -> str | None:
    """ Resolve o telefone final respeitando a intenção do payload """
    update_data = payload.model_dump(exclude_unset=True)
    if "phone_number" not in update_data:
        return user.phone_number
    return payload.phone_number

def get_profile_settings(user: User) -> SettingsProfileResponse:
    """ Retorna o perfil do usuário no formato da tela de configurações """
    return SettingsProfileResponse.model_validate(user)

def get_notification_settings(db: Session, *, user_id: UUID) -> NotificationSettings:
    """ Retorna as preferências globais de notificação para o usuário """
    stored = crud_notifications.get_notification_settings(db, user_id=user_id)
    payload = {
        "email": stored.get(NotificationChannel.email, True),
        "push": stored.get(NotificationChannel.push, False),    
        "sms": stored.get(NotificationChannel.sms, False),
        "whatsapp": stored.get(NotificationChannel.whatsapp, False),
    }
    return NotificationSettings(**payload)

def get_settings_overview(db: Session, user: User) -> SettingsOverviewResponse:
    """ Retorna o resumo completo de configurações para a tela """
    profile = get_profile_settings(user)
    notifications = get_notification_settings(db, user_id=user.id)
    return SettingsOverviewResponse(profile=profile, notifications=notifications)

def update_profile_settings(
    db: Session,
    user: User,
    payload: SettingsProfileUpdate,
    request: Request,
) -> SettingsProfileUpdateResponse:
    """ Atualiza o perfil do usuário e dispara verificações quando necessário """
    try:
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nenhuma alteração informada")

        normalized_email = user.email
        email_changed = False
        if "email" in update_data and payload.email:
            normalized_email = _normalize_email(payload.email)
            if normalized_email != user.email:
                if crud_user.get_user_by_email(db, normalized_email):
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "E-mail já cadastrado")
                email_changed = True

        phone_value = _resolve_phone_for_update(payload, user)
        phone_changed = False
        if phone_value != user.phone_number:
            if phone_value:
                normalized_phone = _normalize_phone(phone_value)
                phone_value = normalized_phone
                if crud_user.get_user_by_phone(db, phone_value):
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Telefone já cadastrado")
            phone_changed = True

        name_value = user.name
        if "name" in update_data and payload.name:
            name_value = payload.name

        if not (email_changed or phone_changed or name_value != user.name):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nenhuma alteração aplicável")
        
        email_verified_value = user.email_verified
        phone_verified_value = user.phone_number_verified
        if email_changed:
            email_verified_value = False
            #Zera a verificação do email para garantir novo fluxo de confirmação
            user.email_verified_at = None
        if phone_changed:
            phone_verified_value = False
            #Reseta o status do telefone ao alterar o número informado
            user.phone_verified_at = None
            
        crud_user.update_user_profile(
            db,
            user,
            name=name_value,
            email=normalized_email,
            phone_number=phone_value,
            email_verified=email_verified_value,
            phone_number_verified=phone_verified_value,
            updated_by=user.id,
        )
        email_verification_required = False
        phone_verification_required = False

        if email_changed:
            token = generate_verification_token()
            expires_at = token_expiry(settings.EMAIL_VERIFICATION_EXPIRE_MINUTES)
            crud_verification.create_verification(
                db,
                user_id=user.id,
                kind=VerificationKind.email,
                raw_token=token,
                expires_at=expires_at,
                metadata={"ip": request.client.host if request.client else "unknown"},
            )
            send_email_verification.delay(str(user.id), token)
            email_verification_required = True

        if phone_changed and phone_value:
            otp = generate_phone_otp()
            expires_at = token_expiry(settings.PHONE_VERIFICATION_EXPIRE_MINUTES)
            crud_verification.create_verification(
                db,
                user_id=user.id,
                kind=VerificationKind.phone_number,
                raw_token=otp,
                expires_at=expires_at,
                attempts_remaining=settings.PHONE_VERIFICATION_MAX_ATTEMPTS,
                metadata={"ip": request.client.host if request.client else "unknown"},
            )
            send_phone_otp.delay(str(user.id), otp)
            phone_verification_required = True

        logger.info(
            "settings_profile_updated",
            user_id=str(user.id),
            email_changed=email_changed,
            phone_changed=phone_changed,
        )

        profile = SettingsProfileResponse.model_validate(user)
        return SettingsProfileUpdateResponse(
            profile=profile,
            email_verification_required=email_verification_required,
            phone_verification_required=phone_verification_required,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("settings_profile_update_failed", user_id=str(user.id))
        raise

def update_notification_settings(
    db: Session,
    user: User,
    payload: NotificationSettings,
) -> NotificationSettings:
    """ Atualiza as preferências de canais de notificação """
    try:
        settings_payload = {
            NotificationChannel.email: payload.email,
            NotificationChannel.push: payload.push,
            NotificationChannel.sms: payload.sms,
            NotificationChannel.whatsapp: payload.whatsapp,
        }

        invalid_channels = set(settings_payload.keys()) - DEFAULT_NOTIFICATION_CHANNELS
        if invalid_channels:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Canal de notificação inválido")
        
        crud_notifications.update_notification_settings(
            db,
            user_id=user.id,
            settings=settings_payload,
        )
        logger.info(
            "settings_notification_updated",
            user_id=str(user.id),
            channels={channel.value: enabled for channel, enabled in settings_payload.items()},
        )
        return NotificationSettings(
            email=payload.email,
            push=payload.push,
            sms=payload.sms,
            whatsapp=payload.whatsapp,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("settings_notification_update_failed", user_id=str(user.id))
        raise
