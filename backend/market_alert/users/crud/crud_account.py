""" Operações de persistência para gestão de contas de usuário """

from uuid import UUID
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from market_alert.models.models_users import User
from market_alert.schemas.schemas_users import UserCreate, UserResponse, UserUpdate
from market_alert.enums.enums_users import UserStatus


logger = structlog.get_logger("users.crud.account")

def get_user_by_email(db: Session, email: str) -> User | None:
    """ Busca usuário por e-mail """
    user = db.query(User).filter(User.email == email).first()
    logger.debug("get_user_by_email", email=email, found=bool(user))
    return user

def get_user_by_phone(db: Session, phone_number: str) -> User | None:
    """ Busca usuário por telefone """
    user = db.query(User).filter(User.phone_number == phone_number).first()
    logger.debug("get_user_by_phone", phone_number=phone_number, found=bool(user))
    return user

def get_user_by_id(db: Session, user_id: UUID) -> User:
    """ Obtém usuário por ID ou lança 404 se não encontrado """
    user = db.get(User, user_id)
    if not user:
        logger.warning("get_user_by_id_not_found", user_id=str(user_id))
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")
    return user

def create_user(db: Session, user_data: UserCreate) -> UserResponse:
    """ Cria usuário pendente com validações de unicidade """
    try:
        #Verifica se o email ou telefone já estão em uso antes de criar o usuário
        if get_user_by_email(db, user_data.email):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="E-mail já cadastrado")
        if user_data.phone_number and get_user_by_phone(db, user_data.phone_number):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Telefone já cadastrado")

        #Cria um usuário novo com senha hasheada
        new_user = User(
            name=user_data.name,
            email=user_data.email,
            phone_number=user_data.phone_number,
            phone_number_verified=False,
            email_verified=False,
            status=UserStatus.pending,
            is_active=True,
            role="user",
            failed_attempts=0,
        )
        new_user.set_password(user_data.password)

        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return UserResponse.model_validate(new_user)
    
    except HTTPException as exc:
        db.rollback()
        raise exc

    except IntegrityError:
        db.rollback()
        logger.exception("integrity_error_create_user", email=user_data.email)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Erro de integridade: E-mail ou telefone já cadastrados")
    
    except Exception:
        db.rollback()
        logger.exception("unexpected_error_create_user", email=user_data.email)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno durante criação de usuário")

def update_user(db: Session, user_id: UUID, updates: UserUpdate) -> UserResponse:
    """ Atualiza dados do usuário existente """
    user = get_user_by_id(db, user_id)
    update_data = updates.model_dump(exclude_unset=True)
    logger.info("update_user_called", user_id=str(user_id), updates=update_data)

    for key, value in update_data.items():
        if key == "password":
            user.set_password(value)
        else:
            setattr(user, key, value)

    db.commit()
    db.refresh(user)
    logger.info("user_update", user_id=str(user.id))
    return UserResponse.model_validate(user)

def update_user_profile(
    db: Session,
    user: User,
    *,
    name: str | None = None,
    email: str | None = None,
    phone_number: str | None = None,
    email_verified: bool | None = None,
    phone_number_verified: bool | None = None,
    updated_by: UUID | None = None,
) -> User:
    """ Atualiza perfil do usuário autenticado com rastreio de alterações """
    changes: dict[str, object] = {}
    
    if name is not None and name != user.name:
        changes["name"] = name
        user.name = name
    
    if email is not None and email != user.email:
        changes["email"] = {"from": user.email, "to": email}
        user.email = email
    
    if phone_number is not None and phone_number != user.phone_number:
        changes["phone_number"] = {"from": user.phone_number, "to": phone_number}
        user.phone_number = phone_number
    
    if email_verified is not None and email_verified != user.email_verified:
        changes["email_verified"] = {"from": user.email_verified, "to": email_verified}
        user.email_verified = email_verified
    
    if phone_number_verified is not None and phone_number_verified != user.phone_number_verified:
        changes["phone_number_verified"] = {"from": user.phone_number_verified, "to": phone_number_verified}
        user.phone_number_verified = phone_number_verified
    
    if updated_by:
        user.updated_by = updated_by

    if changes:
        db.commit()
        db.refresh(user)
        logger.info("user_profile_updated", user_id=str(user.id), changes=changes)
    else:
        logger.info("user_profile_update_skipped", user_id=str(user.id))

    return user

def toggle_user_active(db: Session, user_id: UUID, active: bool) -> UserResponse:
    """ Ativa ou suspende um usuário """
    user = get_user_by_id(db, user_id)
    user.is_active = active
    user.status = UserStatus.active if active else UserStatus.suspended
    db.commit()
    logger.info("user_toggled_active", user_id=str(user.id), active=active)
    return UserResponse.model_validate(user)

def set_email_verified(db: Session, user: User) -> User:
    """ Marca e-mail como verificado """
    user.email_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    logger.info("email_verified_set", user_id=str(user.id))
    return user

def set_phone_verified(db: Session, user: User) -> User:
    """ Marca telefone como verificado """
    user.phone_number_verified = True
    user.phone_verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    logger.info("phone_verified_set", user_id=str(user.id))
    return user

def set_status(db: Session, user: User, status: UserStatus) -> User:
    """ Atualiza status de ciclo de vida da conta """
    user.status = status
    db.commit()
    db.refresh(user)
    logger.info("user_status_updated", user_id=str(user.id), status=status.value)
    return user

def list_users(db: Session, skip: int = 0, limit: int = 10):
    """ Lista usuários de forma paginada """
    users = db.query(User).offset(skip).limit(limit).all()
    logger.debug("list_users", count=len(users), skip=skip, limit=limit)
    return [UserResponse.model_validate(user) for user in users]
