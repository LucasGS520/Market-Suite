""" Funções de acesso e manipulação de usuários """

import structlog
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.models_users import User
from app.schemas.schemas_users import UserResponse, UserCreate, UserUpdate
from app.enums.enums_alerts import AlertType
from app.schemas.schemas_alert_rules import AlertRuleCreate
from app.crud import crud_alert_rules


logger = structlog.get_logger("crud.user")

def get_user_by_email(db: Session, email: str) -> User | None:
    """ Busca um usuário pelo email """
    user = db.query(User).filter(User.email == email).first()
    logger.debug("get_user_by_email", email=email, found=bool(user))
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
        existing_phone = db.query(User).filter(User.phone_number == user_data.phone_number).first()
        if existing_phone:
            logger.warning("phone_in_use", phone=user_data.phone_number)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Telefone já cadastrado")

        #Cria o usuário com senha hasheada
        new_user = User(
            name=user_data.name,
            email=user_data.email,
            phone_number=user_data.phone_number,
            notifications_enabled=user_data.notifications_enabled,
            is_active=True,
            is_email_verified=False,
            role="user",
            failed_attempts=0
        )
        new_user.set_password(user_data.password) #Armazena a senha corretamente

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        #Cria regra de alerta padrão para novos usuários
        crud_alert_rules.create_alert_rule(
            db,
            AlertRuleCreate(
                user_id=new_user.id,
                rule_type=AlertType.PRICE_TARGET,
                enabled=True
            )
        )

        logger.info("user_created", user_id=str(new_user.id))
        return UserResponse.model_validate(new_user)

    except IntegrityError as e:
        db.rollback()  #Reverte a transação caso haja erro de integridade
        logger.error("integrity_error_create_user", error=str(e))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Erro de integridade: E-mail ou telefone já cadastrados")

    except Exception as e:
        db.rollback()
        logger.exception("unexpected_error_create_user", error=str(e))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro interno: {str(e)}")

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
    db.commit()
    logger.info("user_toggled_active", user_id=str(user.id), active=active)
    return UserResponse.model_validate(user)

def list_users(db: Session, skip: int = 0, limit: int = 10):
    """ Lista usuários de forma paginada """
    users = db.query(User).offset(skip).limit(limit).all()
    logger.debug("list_users", count=len(users), skip=skip, limit=limit)
    return [UserResponse.model_validate(user) for user in users]
