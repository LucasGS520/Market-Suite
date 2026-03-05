""" Operações de persistência para tokens e OTPs de verificação """

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from market_alert.core.tokens import hash_token
from market_alert.models.models_verification import Verification
from market_alert.enums.enums_users import VerificationKind


logger = structlog.get_logger("users.crud.identity")

def create_verification(
    db: Session,
    *,
    user_id: UUID,
    kind: VerificationKind,
    raw_token: str,
    expires_at: datetime,
    attempts_remaining: int | None = None,
    metadata: dict | None = None,
) -> Verification:
    """ Cria verificação com token hasheado para segurança em repouso """
    token_hash = hash_token(raw_token)
    verification = Verification(
        user_id=user_id,
        kind=kind,
        token_hash=token_hash if kind == VerificationKind.email else None,
        otp_hash=token_hash if kind == VerificationKind.phone_number else None,
        expires_at=expires_at,
        attempts=0,
        attempts_remaining=attempts_remaining,
        metadata=metadata,
    )
    db.add(verification)
    db.commit()
    db.refresh(verification)
    logger.info(
        "verification_created",
        user_id=str(user_id),
        kind=kind.value,
        expires_at=expires_at.isoformat(),
    )
    return verification

def get_active_by_user(db: Session, user_id: UUID, kind: VerificationKind) -> Verification | None:
    """ Obtém token ativo mais recente por usuário e tipo """
    now = datetime.now(timezone.utc)
    return (
        db.query(Verification)
        .filter(Verification.user_id == user_id)
        .filter(Verification.kind == kind)
        .filter(Verification.expires_at >= now)
        .filter(Verification.consumed_at.is_(None))
        .order_by(Verification.created_at.desc())
        .first()
    )

def consume_verification(
    db: Session,
    *,
    kind: VerificationKind,
    raw_token: str,
    user_id: UUID | None = None,
) -> Verification | None:
    """ Consome token válido e impede reutilização """
    now = datetime.now(timezone.utc)
    token_hash = hash_token(raw_token)
    query = (
        db.query(Verification)
        .filter(Verification.kind == kind)
        .filter(
            Verification.token_hash == token_hash
            if kind == VerificationKind.email
            else Verification.otp_hash == token_hash
        )
        .filter(Verification.consumed_at.is_(None))
        .filter(Verification.expires_at >= now)
    )
    if user_id:
        query = query.filter(Verification.user_id == user_id)
    verification = query.first()
    if not verification:
        logger.warning("verification_not_found", kind=kind.value)
        return None
    verification.consumed_at = now
    db.commit()
    db.refresh(verification)
    logger.info("verification_consumed", id=str(verification.id), kind=kind.value)
    return verification

def increment_attempts(db: Session, verification: Verification) -> Verification:
    """ Incrementa tentativas inválidas e reduz saldo restante do OTP """
    verification.attempts += 1
    if verification.attempts_remaining is not None:
        verification.attempts_remaining = max(verification.attempts_remaining - 1, 0)
    db.commit()
    db.refresh(verification)
    logger.info(
        "verification_attempt_incremented",
        id=str(verification.id),
        attempts=verification.attempts,
        attempts_remaining=verification.attempts_remaining,
    )
    return verification
