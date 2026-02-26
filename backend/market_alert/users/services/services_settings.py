""" Casos de uso para preferências e configurações do usuário """

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from market_alert.core.config_alert import settings
from market_alert.core.tokens import generate_phone_otp, generate_verification_token, token_expiry
from market_alert.models.models_users import User
from market_alert.schemas.schemas_settings import (
    NotificationSettings,
    SettingsOverviewResponse,
    SettingsProfileResponse,
    SettingsProfileUpdate,
    SettingsProfileUpdateResponse,
)
from market_alert.enums.enums_notifications import NotificationChannel
from market_alert.enums.enums_users import VerificationKind
from market_alert.users.crud import crud_account, crud_identity
from market_alert.crud import crud_notifications
from market_alert.users.domain.account_domain import normalize_email, normalize_phone
from market_alert.users.domain.settings_domain import DEFAULT_NOTIFICATION_CHANNELS
from backend.market_alert.users.tasks.verification_tasks import send_email_verification, send_phone_otp


logger = structlog.get_logger("users.services.settings")

def get_profile_settings(user: User) -> SettingsProfileResponse:
    """ Converte usuário autenticado para payload de perfil """
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

def _resolve_phone_for_update(payload: SettingsProfileUpdate, user: User) -> str | None:
    """ Resolve o telefone final respeitando a intenção do payload """
    update_data = payload.model_dump(exclude_unset=True)
    if "phone_number" not in update_data:
        return user.phone_number
    return payload.phone_number

def update_profile_settings(
    db: Session,
    user: User,
    payload: SettingsProfileUpdate,
    request: Request,
) -> SettingsProfileUpdateResponse:
    """ Atualiza perfil e dispara novas verificações para campos sensíveis """
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nenhuma alteração informada")

    normalized_email = user.email
    email_changed = False
    if "email" in update_data and payload.email:
        normalized_email = normalize_email(payload.email)
        if normalized_email != user.email:
            if crud_account.get_user_by_email(db, normalized_email):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "E-mail já cadastrado")
            email_changed = True

    phone_value = _resolve_phone_for_update(payload, user)
    phone_changed = False
    if phone_value != user.phone_number:
        if phone_value:
            phone_value = normalize_phone(phone_value)
            if crud_account.get_user_by_phone(db, phone_value):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Telefone já cadastrado")
        phone_changed = True

    name_value = payload.name if "name" in update_data and payload.name else user.name
    if not (email_changed or phone_changed or name_value != user.name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nenhuma alteração aplicável")

    email_verified_value = user.email_verified
    phone_verified_value = user.phone_number_verified
    if email_changed:
        #Troca de e-mail invalida a confirmação anterior por segurança.
        email_verified_value = False
        user.email_verified_at = None
    if phone_changed:
        #Troca de telefone também reinicia o estado de confiança desse fator.
        phone_verified_value = False
        user.phone_verified_at = None

    crud_account.update_user_profile(
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
        crud_identity.create_verification(
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
        crud_identity.create_verification(
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

    profile = get_profile_settings(user)
    return SettingsProfileUpdateResponse(
        profile=profile,
        email_verification_required=email_verification_required,
        phone_verification_required=phone_verification_required,
    )

def update_notification_settings(
    db: Session,
    user: User,
    payload: NotificationSettings,
) -> NotificationSettings:
    """ Atualiza preferências globais de canais de comunicação """
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
