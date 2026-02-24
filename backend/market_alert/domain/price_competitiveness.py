""" Camada de domínio — Regras de competitividade de preços

Responsabilidade única: calcular se um produto monitorado é competitivo
frente aos seus concorrentes, com base em limiares configuráveis.

Regras desta camada:
- Não importa de: services, crud, orchestrator, tasks, routes, FastAPI, SQLAlchemy
- Não acessa banco de dados, Redis ou qualquer I/O externo
- Funções recebem dados já carregados e retornam resultados estruturados
- Testável com pytest puro, sem mocks de infraestrutura
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from market_alert.enums.enums_comparisons import CompetitivenessStatus

if TYPE_CHECKING:
    from market_alert.core.config_alert import Settings


__all__ = [
    "CompetitivenessThresholds",
    "ComparisonSnapshot",
    "CompetitivenessResult",
    "determine_competitiveness_status",
    "calculate_competitiveness",
]


@dataclass(frozen=True)
class CompetitivenessThresholds:
    """ Limiares percentuais para classificar a competitividade do monitorado.

    Atributos:
        non_competitive_pct: Limite superior da faixa de 'atenção baixa'.
            Diferenças de 0% até este valor ainda são classificadas como
            atenção (não urgente). Padrão: 1%.
        attention_pct: Limite superior da faixa de atenção.
            Diferenças acima deste valor tornam-se urgentes. Padrão: 5%.
        urgent_pct: Referência do limiar urgente — usado para documentação
            e possível extensão futura de sub-faixas. Padrão: 20%.

    Exemplos de classificação com valores padrão:
        delta ≤ 0%   → competitivo
        0% < delta ≤ 5%  → atenção
        delta > 5%   → urgente
    """
    non_competitive_pct: Decimal
    attention_pct: Decimal
    urgent_pct: Decimal = Decimal("20")

    @classmethod
    def from_config(cls, settings: "Settings") -> "CompetitivenessThresholds":
        """ Cria instância lendo os limiares das configurações da aplicação.

        Args:
            settings: Instância de Settings carregada com variáveis de ambiente.

        Returns:
            CompetitivenessThresholds com valores do ambiente ou padrões.
        """
        return cls(
            non_competitive_pct=Decimal(
                str(settings.COMPETITIVENESS_THRESHOLD_NON_COMPETITIVE_PCT)
            ),
            attention_pct=Decimal(
                str(settings.COMPETITIVENESS_THRESHOLD_ATTENTION_PCT)
            ),
            urgent_pct=Decimal(
                str(settings.COMPETITIVENESS_THRESHOLD_URGENT_PCT)
            ),
        )

    @classmethod
    def defaults(cls) -> "CompetitivenessThresholds":
        """ Fallback com limiares padrão quando settings não está disponível.

        Útil em testes unitários que não precisam carregar o ambiente completo.
        """
        return cls(
            non_competitive_pct=Decimal("1"),
            attention_pct=Decimal("5"),
            urgent_pct=Decimal("20"),
        )

    def __repr__(self) -> str:
        return (
            f"CompetitivenessThresholds("
            f"non_competitive={self.non_competitive_pct}%, "
            f"attention={self.attention_pct}%, "
            f"urgent={self.urgent_pct}%)"
        )

@dataclass
class ComparisonSnapshot:
    """ Dados necessários para calcular competitividade — sem dependência de ORM.

    Encapsula os preços do produto monitorado e dos concorrentes disponíveis.
    Nenhum campo referencia modelos de banco de dados.

    Atributos:
        monitored_price: Preço atual do produto monitorado. None indica que o produto não tem preço coletado.
        competitor_prices: Lista de preços válidos dos concorrentes. Deve conter apenas Decimals já convertidos e validados.
        competitor_availability: Disponibilidade de cada concorrente, alinhada por índice com competitor_prices. 
        None = todos disponíveis.
    """
    monitored_price: Optional[Decimal]
    competitor_prices: List[Decimal]
    competitor_availability: Optional[List[bool]] = None

    def is_valid(self) -> bool:
        """ Retorna True se há dados suficientes para calcular competitividade.

        Um snapshot válido requer preço do monitorado E ao menos um concorrente.
        """
        return self.monitored_price is not None and bool(self.competitor_prices)

    def available_prices(self) -> List[Decimal]:
        """ Retorna preços dos concorrentes disponíveis.

        Se competitor_availability não foi informado, assume que todos
        os preços da lista são válidos e os retorna integralmente.

        Returns:
            Lista de Decimals com preços de concorrentes elegíveis.
        """
        if self.competitor_availability is None:
            return list(self.competitor_prices)
        return [
            price
            for price, available in zip(self.competitor_prices, self.competitor_availability)
            if available
        ]

@dataclass
class CompetitivenessResult:
    """ Resultado do cálculo de competitividade — sem referência a ORM ou persistência.

    Atributos:
        status: Valor do enum CompetitivenessStatus (ex: "competitivo", "urgente").
        monitored_price: Preço do produto monitorado usado no cálculo.
        min_price: Menor preço entre os concorrentes disponíveis.
        mean_price: Média dos preços dos concorrentes (2 casas decimais).
        max_price: Maior preço entre os concorrentes disponíveis.
        rank: Posição do monitorado no ranking de preços (1 = mais barato).
        adjustment: Quanto reduzir para igualar o menor concorrente. None se já
            estiver competitivo ou abaixo.
        details: Campos extras para extensão futura.
    """
    status: str
    monitored_price: Decimal
    min_price: Optional[Decimal]
    mean_price: Optional[Decimal]
    max_price: Optional[Decimal]
    rank: Optional[int]
    adjustment: Optional[Decimal]
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """ Serializa o resultado para dicionário compatível com o resumo de comparação.

        Os nomes das chaves correspondem exatamente aos campos esperados pelo
        schema PriceComparisonSummaryResponse e pelo snapshot de notificações.

        Returns:
            Dict com campos de competitividade prontos para persistência ou
            inclusão no payload de resposta da API.
        """
        return {
            "competitiveness_status": self.status,
            "monitored_price": self.monitored_price,
            "competitors_min": self.min_price,
            "competitors_mean": self.mean_price,
            "competitors_max": self.max_price,
            "position_rank": self.rank,
            "potential_adjustment": self.adjustment,
            **self.details,
        }

def determine_competitiveness_status(
    delta_percent: Decimal,
    thresholds: CompetitivenessThresholds,
) -> str:
    """ Classifica um delta percentual em um status de competitividade.

    Função pura: sem I/O, sem efeitos colaterais. Recebe apenas números
    e retorna um valor de string correspondente ao enum CompetitivenessStatus.

    Regras de classificação:
        delta ≤ 0                         → COMPETITIVE (monitorado abaixo ou igual)
        0 < delta ≤ attention_pct (5%)    → ATTENTION
        delta > attention_pct             → URGENT

    Args:
        delta_percent: Diferença percentual calculada como
            ((monitored_price - min_competitor_price) / min_competitor_price) * 100.
            Valores positivos indicam que o monitorado está ACIMA do menor concorrente.
        thresholds: Limiares configurados para a classificação.

    Returns:
        str: valor do membro CompetitivenessStatus correspondente.

    Exemplos:
        >>> thresholds = CompetitivenessThresholds.defaults()
        >>> determine_competitiveness_status(Decimal("0"), thresholds)
        'competitivo'
        >>> determine_competitiveness_status(Decimal("-5"), thresholds)
        'competitivo'
        >>> determine_competitiveness_status(Decimal("3"), thresholds)
        'atencao'
        >>> determine_competitiveness_status(Decimal("10"), thresholds)
        'urgente'
    """
    if delta_percent <= Decimal("0"):
        return CompetitivenessStatus.COMPETITIVE.value

    if delta_percent <= thresholds.attention_pct:
        return CompetitivenessStatus.ATTENTION.value

    return CompetitivenessStatus.URGENT.value

def calculate_competitiveness(
    snapshot: ComparisonSnapshot,
    thresholds: CompetitivenessThresholds,
) -> CompetitivenessResult:
    """ Calcula competitividade a partir de um snapshot de preços.

    Função pura: sem I/O, sem ORM, sem acesso a banco de dados.
    Recebe todos os dados como argumentos e retorna um resultado estruturado.

    Sequência de cálculo:
        1. Valida o snapshot (raises ValueError se inválido)
        2. Filtra preços disponíveis
        3. Calcula min, max, mean
        4. Calcula position_rank (1 + quantidade de concorrentes mais baratos)
        5. Calcula potential_adjustment (diferença para o menor preço)
        6. Calcula delta percentual frente ao menor concorrente
        7. Classifica status via determine_competitiveness_status()

    Args:
        snapshot: Preços do monitorado e dos concorrentes disponíveis.
        thresholds: Limiares para classificação do status.

    Returns:
        CompetitivenessResult com status, ranking e métricas calculadas.

    Raises:
        ValueError: Se o snapshot não contiver dados suficientes para cálculo
            (monitored_price ausente ou lista de concorrentes vazia).

    Exemplos:
        >>> thresholds = CompetitivenessThresholds.defaults()
        >>> snapshot = ComparisonSnapshot(
        ...     monitored_price=Decimal("100.00"),
        ...     competitor_prices=[Decimal("90.00"), Decimal("95.00")],
        ... )
        >>> result = calculate_competitiveness(snapshot, thresholds)
        >>> result.status
        'urgente'
        >>> result.rank
        3
        >>> result.adjustment
        Decimal('10.00')
    """
    if not snapshot.is_valid():
        raise ValueError(
            "ComparisonSnapshot inválido: monitored_price e ao menos um "
            "competitor_price são obrigatórios para o cálculo."
        )

    prices = snapshot.available_prices()
    monitored = snapshot.monitored_price

    if not prices:
        raise ValueError(
            "Nenhum preço de concorrente disponível após filtrar por disponibilidade."
        )

    min_price = min(prices)
    max_price = max(prices)
    mean_price = (sum(prices) / len(prices)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    #Posição no ranking: 1 + quantidade de concorrentes com preço menor que o monitorado
    cheaper_count = sum(1 for p in prices if p < monitored)
    rank = cheaper_count + 1

    #Ajuste necessário para igualar o menor concorrente (None se já está competitivo)
    adjustment = None
    if monitored > min_price:
        adjustment = (monitored - min_price).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    #Delta percentual frente ao menor concorrente para classificação do status
    try:
        if min_price > Decimal("0"):
            delta_fraction = (monitored - min_price) / min_price
            delta_percent = (delta_fraction * Decimal("100")).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        else:
            delta_percent = Decimal("0")
    except (InvalidOperation, ZeroDivisionError):
        delta_percent = Decimal("0")

    status = determine_competitiveness_status(delta_percent, thresholds)

    return CompetitivenessResult(
        status=status,
        monitored_price=monitored,
        min_price=min_price,
        mean_price=mean_price,
        max_price=max_price,
        rank=rank,
        adjustment=adjustment,
    )
