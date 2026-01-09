""" Funções de acesso e manipulação de usuários """

import structlog
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from market_alert.enums.enums_users import UserStatus
from market_alert.models.models_users import User
from market_alert.schemas.schemas_users import UserResponse, UserCreate, UserUpdate


logger = structlog.get_logger("crud.user")

def get_user_by_email(db: Session, email: str) -> User | None:
    """ Busca um usuário pelo email """
    user = db.query(User).filter(User.email == email).first()
    logger.debug("get_user_by_email", email=email, found=bool(user))
    return user

def get_user_by_phone(db: Session, phone_number: str) -> User | None:
    """ Busca um usuário pelo número de telefone """
    user = db.query(User).filter(User.phone_number == phone_number).first()
    logger.debug("get_user_by_phone", phone_number=phone_number, found=bool(user))
    return user

def get_user_by_id(db: Session, user_id: UUID) -> User:
    """ Obtém um usuário pelo ID ou dispara 404 se não encontrado """
    user = db.get(User, user_id)
    if not user:
        logger.warning("get_user_by_id_not_found", user_id=str(user_id))
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")
    logger.debug("get_user_by_id", user_id=str(user_id))
    return user


def create_user(db: Session, user_data: UserCreate) -> UserResponse:
    """ Cria um usuário realizando validações básicas """
    logger.info("create_user_called", email=user_data.email)
    try:
        #Verifica se o email já existe no banco
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            logger.warning("email_in_use", email=user_data.email)
            raise HTTPException(status_code=400, detail="E-mail já cadastrado")

        #Verifica se o telefone já esta cadastrado
        if user_data.phone_number:
            existing_phone = db.query(User).filter(User.phone_number == user_data.phone_number).first()
            if existing_phone:
                logger.warning("phone_in_use", phone=user_data.phone_number)
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Telefone já cadastrado")

        #Cria o usuário com senha hasheada
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
        new_user.set_password(user_data.password) #Armazena a senha corretamente

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.info("user_created", user_id=str(new_user.id))
        return UserResponse.model_validate(new_user)

    except HTTPException as exc:
        db.rollback()
        #Preserva a semântica de validação para evitar mascarar erros HTTP esperados
        raise exc

    except IntegrityError:
        db.rollback()  #Reverte a transação caso haja erro de integridade
        logger.exception("integrity_error_create_user", email=user_data.email)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Erro de integridade: E-mail ou telefone já cadastrados")

    except Exception:
        db.rollback()
        logger.exception("unexpected_error_create_user", email=user_data.email)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno durante criação de usuário")

def update_user(db: Session, user_id: UUID, updates: UserUpdate) -> UserResponse:
    """ Atualiza os Dados de um usuário existente """
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

def toggle_user_active(db: Session, user_id: UUID, active: bool) -> UserResponse:
    """ Ativa ou Desativa um usuário """
    user = get_user_by_id(db, user_id)
    user.is_active = active
    user.status = UserStatus.active if active else UserStatus.suspended
    db.commit()
    logger.info("user_toggled_active", user_id=str(user.id), active=active)
    return UserResponse.model_validate(user)

def set_email_verified(db: Session, user: User) -> User:
    """ Marca o email como verificado e atualiza timestamp """
    user.email_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    logger.info("email_verified_set", user_id=str(user.id))
    return user

def set_phone_verified(db: Session, user: User) -> User:
    """ Marca o telefone como verificado e atualiza timestamp """
    user.phone_number_verified = True
    user.phone_verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    logger.info("phone_verified_set", user_id=str(user.id))
    return user

def set_status(db: Session, user: User, status: UserStatus) -> User:
    """ Ajusta o status da conta """
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
