"""Regras de negócio puras para o ciclo de vida de produtos monitorados.

Esta camada é agnóstica a infraestrutura: não acessa banco, Redis ou filas.
Recebe objetos de modelo ORM e retorna decisões sem efeitos colaterais externos.

Responsabilidades:
- Resolver evento de agendamento (preço, disponibilidade, padrão)
- Calcular próximo check_at delegando para interval_calculator_products
- Validar transições de status entre estados do monitorado
- Atualizar rastreamento de preço nos objetos de produto (sem commit)

NÃO importa de: services, crud, orchestrator, tasks, Redis, FastAPI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import structlog

from market_alert.enums.enums_products import MonitoredStatus
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.products.utils.interval_calculator_products import (
    EVENT_AVAILABILITY_CHANGED,
    EVENT_PRICE_CHANGED,
    EVENT_STANDARD,
    STABILITY_UNSTABLE,
    RetryContext,
    SchedulingDecision,
    calculate_schedule,
)
from market_alert.products.utils.price_decimal import different_price


logger = structlog.get_logger("domain.product_lifecycle")

#Transições de status explicitamente permitidas pelas regras de negócio.
#Qualquer transição não listada aqui deve ser rejeitada pelo service.
_ALLOWED_STATUS_TRANSITIONS: dict[MonitoredStatus, set[MonitoredStatus]] = {
    MonitoredStatus.pending: {
        MonitoredStatus.active,
        MonitoredStatus.inactive,
        MonitoredStatus.failed,
    },
    MonitoredStatus.active: {
        MonitoredStatus.inactive,
        MonitoredStatus.failed,
    },
    MonitoredStatus.inactive: {
        MonitoredStatus.active,
        MonitoredStatus.failed,
    },
    #Produto em falha só volta ao ciclo via restart explícito (pending)
    MonitoredStatus.failed: {
        MonitoredStatus.pending,
    },
}

def resolve_scheduling_event(
    *,
    price_changed: bool,
    availability_changed: bool,
) -> str:
    """ Define o evento de agendamento priorizando mudanças mais sensíveis.

    A ordem de precedência evita ambiguidade quando preço e disponibilidade
    mudam no mesmo ciclo: priorizamos preço por representar alteração com maior
    impacto no loop de comparação.

    Args:
        price_changed: True se o preço atual difere do anterior.
        availability_changed: True se o status de disponibilidade mudou.

    Returns:
        Uma das constantes EVENT_* de interval_calculator_products.
    """
    if price_changed:
        return EVENT_PRICE_CHANGED
    if availability_changed:
        return EVENT_AVAILABILITY_CHANGED
    return EVENT_STANDARD

def compute_next_check_at(
    product: MonitoredProduct,
    *,
    reference_time: datetime | None = None,
    event_type: str = EVENT_STANDARD,
    retry_context: RetryContext | None = None,
) -> SchedulingDecision:
    """ Calcula a próxima janela de agendamento delegando para a política centralizada.

    Centraliza o acesso à política de agendamento de modo que CRUD e services
    não precisem importar interval_calculator_products diretamente.

    Args:
        product: Instância do monitorado a ser agendada.
        reference_time: Tempo-base do cálculo (ex.: momento da coleta).
        event_type: Evento que disparou o recálculo (preço, disponibilidade, padrão).
        retry_context: Contexto opcional para fluxos de retry/cooldown.

    Returns:
        SchedulingDecision com next_check_at, stability_score, intervalo e motivo.
    """
    return calculate_schedule(
        product,
        reference_time=reference_time,
        event_type=event_type,
        retry_context=retry_context,
    )

def validate_status_transition(
    current_status: MonitoredStatus,
    target_status: MonitoredStatus,
) -> bool:
    """ Valida se a transição entre status é permitida pelas regras de negócio.

    Evita transições inválidas como ativar diretamente um produto em falha
    sem operação explícita de restart, ou regredir estado arbitrariamente.

    Args:
        current_status: Status atual do monitorado.
        target_status: Status desejado após a operação.

    Returns:
        True se a transição é permitida, False caso contrário.
    """
    allowed = _ALLOWED_STATUS_TRANSITIONS.get(current_status, set())
    return target_status in allowed

def update_price_change_tracking(
    monitored: MonitoredProduct,
    new_price: Decimal | None,
    old_price: Decimal | None,
    collected_at: datetime,
) -> None:
    """ Atualiza rastreio de mudança de preço no objeto monitorado sem commit.

    Marca group_collected_at para sincronizar o grupo de coleta e, quando o
    preço efetivamente muda, reseta stability_score para UNSTABLE a fim de
    acelerar rechecagens no ciclo imediatamente seguinte.

    Args:
        monitored: Instância ORM do monitorado (será mutada in-place, sem commit).
        new_price: Preço obtido na coleta atual.
        old_price: Preço registrado antes desta coleta.
        collected_at: Timestamp da coleta utilizado como referência.
    """
    collected_reference = (
        collected_at.astimezone(timezone.utc)
        if collected_at.tzinfo
        else collected_at.replace(tzinfo=timezone.utc)
    )
    monitored.group_collected_at = collected_reference

    if different_price(old_price, new_price):
        # Resetamos estabilidade para acelerar rechecagem após mudança de preço
        monitored.last_price_change_at = collected_reference
        monitored.stability_score = STABILITY_UNSTABLE
        logger.info(
            "monitored_price_change_detected",
            monitored_id=str(monitored.id),
            old_price=str(old_price) if old_price is not None else None,
            new_price=str(new_price) if new_price is not None else None,
            collected_at=collected_reference.isoformat(),
        )

def update_competitor_price_change_tracking(
    competitor: CompetitorProduct,
    new_price: Decimal | None,
    old_price: Decimal | None,
    collected_at: datetime,
) -> None:
    """ Atualiza o registro de mudança de preço do concorrente sem commit.

    Registra last_price_change_at quando o preço efetivamente muda,
    permitindo que a política de estabilidade do monitorado seja computada
    com base em toda a cadeia de preços do ecossistema.

    Args:
        competitor: Instância ORM do concorrente (será mutada in-place, sem commit).
        new_price: Preço obtido na coleta atual.
        old_price: Preço registrado antes desta coleta.
        collected_at: Timestamp da coleta utilizado como referência.
    """
    collected_reference = (
        collected_at.astimezone(timezone.utc)
        if collected_at.tzinfo
        else collected_at.replace(tzinfo=timezone.utc)
    )
    if different_price(old_price, new_price):
        competitor.last_price_change_at = collected_reference
        logger.info(
            "competitor_price_change_detected",
            competitor_id=str(competitor.id),
            monitored_id=str(competitor.monitored_product_id),
            old_price=str(old_price) if old_price is not None else None,
            new_price=str(new_price) if new_price is not None else None,
            collected_at=collected_reference.isoformat(),
        )
