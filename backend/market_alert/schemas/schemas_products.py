""" Esquemas Pydantic exclusivos do serviço `market_alert` """

from typing import Literal, Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from market_alert.enums.enums_comparisons import CompetitivenessStatus
from market_alert.schemas.schemas_comparisons import PriceComparisonSummaryResponse


class ProductResponse(BaseModel):
    """ Visão simplificada do produto exposta pela API pública """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str | None = Field(None, description="Nome original cadastrado/coletado sem ajustes de fallback")
    name: str = Field(..., description="Nome preparado para exibição")
    url: HttpUrl = Field(..., description="Endereço canônico do produto")
    current_price: Decimal | None = Field(None, description="Preço para exibição quando disponível")
    currency: Optional[str] = Field(None, description="Moeda do preço informado")
    source: Literal["monitored", "competitor"]
    availability: bool | None = Field(None, description="Disponibilidade reportada pelo fluxo de coleta")
    last_status: str | None = Field(None, description="Status mais recente conhecido do fluxo de coleta")
    last_checked: datetime | None = Field(None, description="Momento da última checagem conhecida do produto")

# ----- RETORNOS DE CADASTRO -----
class MonitoredScrapeCreationResponse(BaseModel):
    """ Retorno mínimo ao agendar scraping de produto monitorado """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Identificador do produto monitorado")
    url: HttpUrl = Field(..., description="URL normalizada usada no monitoramento")
    created_at: datetime = Field(..., description="Momento de criação do registro")
    next_check_at: datetime = Field(..., description="Próximo horário previsto para a primeira rechecagem")
    message: str = Field(..., description="Resumo amigável do agendamento")

class CompetitorScrapeCreationResponse(BaseModel):
    """ Retorno mínimo ao agendar scraping de um concorrente """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Identificador do concorrente pendente")
    url: HttpUrl = Field(..., description="Endereço canônico normalizado")
    created_at: datetime = Field(..., description="Momento de criação do registro")
    message: str = Field(..., description="Resumo amigável do agendamento")

# ----- PRODUTO MONITORADO -----
class MonitoredProductResponse(ProductResponse):
    """ Contrato simplificado de um produto monitorado """
    owner_id: UUID = Field(..., description="Identificador do responsável pelo monitoramento")
    source: Literal["monitored"] = "monitored"
    display_status: Literal[
        "inactive",
        "paused",
        "collecting",
        "no_price",
        "no_competitors",
        "competitive",
        "attention",
        "urgent",
        "unknown",
    ] | None = Field(
        None,
        description=(
            "Status consolidado para exibição, priorizando disponibilidade, pausa e competitividade "
            "sem depender apenas do `competitiveness_status` legado."
        ),
    )
    thumbnail: str | None = Field(None, description="Miniatura mais recente identificada pelo fluxo de scraping")
    created_at: datetime | None = Field(None, description="Momento de criação do monitoramento (timestamp do cadastro)")
    last_scraped_at: datetime | None = Field(None, description="Momento da última extração concluída para o produto")
    last_collected_at: datetime | None = Field(None, description="Momento da última tentativa de coleta concluída (alias para `last_scraped_at`, exposto para clareza no frontend)")
    next_check_at: datetime | None = Field(None, description="Próximo horário previsto para rechecagem do produto")
    last_price_change_at: datetime | None = Field(None, description="Última vez em que o preço monitorado mudou")
    stability: str | None = Field(None, description="Classificação de estabilidade derivada da pontuação interna, usada para ajustar frequências de coleta")
    monitored_since: datetime | None = Field(None, description="Momento em que o monitoramento foi iniciado (alias para `created_at`)")
    last_price_change_global_at: datetime | None = Field(None, description=("Última mudança de preço considerando histórico do monitorado e de todos os concorrentes vinculados"))
    competitiveness_status: CompetitivenessStatus | None = Field(None, description="Classificação de competitividade calculada a partir das comparações")
    is_featured: bool = Field(False, description="Indica se o item deve ser exibido como destaque")
    paused: bool = Field(False, description="Indica se o monitoramento está pausado para evitar novas coletas")
    paused_at: datetime | None = Field(None, description="Momento em que a pausa foi ativada, quando existir")
    comparison_summary: PriceComparisonSummaryResponse | None = Field(
        default=None,
        description=("Último resumo consolidado de comparação de preços com métricas normalizadas para exibição imediata no frontend."),
    )

class MonitoredPausedUpdateRequest(BaseModel):
    """ Requisição para alternar estado de pausa de um monitorado de forma idempotente """
    paused: bool = Field(..., description="Define se o monitoramento deve ficar pausado ou ativo")

class PaginationMeta(BaseModel):
    """ Metadados padronizados para paginação de listagens."""
    total: int = Field(..., description="Quantidade total de registros disponíveis")
    page: int = Field(..., description="Página atual baseada em 1")
    per_page: int = Field(..., description="Quantidade de registros por página")

class PaginatedMonitoredProductsResponse(BaseModel):
    """ Envelope de paginação para produtos monitorados """
    items: list[MonitoredProductResponse]
    meta: PaginationMeta

# ----- PRODUTO CONCORRENTE -----
class CompetitorProductResponse(ProductResponse):
    """ Contrato simplificado de um produto concorrente """
    last_scraped_at: datetime | None = Field(None, description="Momento da última extração concluída para o concorrente")
    monitored_product_id: UUID = Field(
        ..., description="Vínculo obrigatório com o produto monitorado"
    )
    source: Literal["competitor"] = "competitor"
    is_paused: bool = Field(False, description="Indica se o monitoramento do concorrente está pausado")

class PaginatedCompetitorResponse(BaseModel):
    """ Envelope padronizado para retornar concorrentes paginados com metadados """
    items: list[CompetitorProductResponse]
    meta: PaginationMeta

class CompetitorsListResponse(BaseModel):
    """ Lista concorrentes e expõe contadores úteis para a UI """

    items: list[CompetitorProductResponse]
    competitors_total: int = Field(
        ..., description="Quantidade total de concorrentes vinculados ao monitorado"
    )
    competitors_with_price_count: int = Field(
        ..., description="Concorrentes com preço utilizável em métricas e comparações"
    )
    excluded_due_to_inactive_count: int = Field(
        ...,
        description=(
            "Concorrentes ignorados em cálculos por falta de preço ou indisponibilidade"
        ),
    )
    page: int = Field(..., description="Página atual baseada em 1")
    per_page: int = Field(..., description="Quantidade de registros retornados por página")
