""" Utilitário de comparação de snapshots para idempotência de resumos

Responsabilidade única: determinar se um resumo de comparação mudou
materialmente desde a última vez que foi persistido.

Campos "materiais" são aqueles que indicam mudança real no cenário
competitivo. Timestamps são ignorados propositalmente — uma mudança de
relógio sem alteração de preços não deve disparar uma nova persistência.

Regras desta camada:
- Não importa de: services, crud, models, ORM, FastAPI, Celery
- Não acessa banco de dados nem qualquer I/O externo
- Funções são puras: mesmo input → mesmo output, sem efeitos colaterais
- Testável com pytest puro, sem mocks de infraestrutura

Uso típico:
    current = extract_material_snapshot(new_summary_dict)
    previous = extract_material_snapshot(stored_summary.aggregates)
    if snapshot_has_changed(current, previous):
        # persistir novo resumo
        ...
"""

from typing import Any, Dict, Optional


__all__ = [
    "extract_material_snapshot",
    "snapshot_has_changed",
    "MATERIAL_FIELDS",
]

#Campos que representam mudança real no cenário competitivo.
#Timestamps (last_comparison_at, computed_at) são excluídos propositalmente
#para evitar persistências desnecessárias quando apenas o relógio muda.
MATERIAL_FIELDS: tuple[str, ...] = (
    "comparison_id",              #UUID da comparação mais recente
    "monitored_price",            #Preço do produto monitorado
    "competitors_count",          #Total de concorrentes cadastrados
    "competitors_with_price_count", #Concorrentes com preço válido
    "competitors_mean",           #Média dos preços dos concorrentes
    "competitors_min",            #Menor preço entre concorrentes
    "competitors_max",            #Maior preço entre concorrentes
    "position_rank",              #Posição do monitorado no ranking
    "potential_adjustment",       #Quanto reduzir para igualar o menor
    "ignored_due_to_inactive",    #Monitorado sem preço ou indisponível
    "competitiveness_status",     #competitivo | atencao | urgente
    "comparison_insights",        #Texto explicativo para o frontend
    "discrepancies",              #Lista de discrepâncias por concorrente
    "reason",                     #Motivo de ausência de comparação
)

def extract_material_snapshot(payload: Any) -> Dict[str, Any]:
    """ Extrai apenas os campos materiais de um resumo de comparação.

    Ignora timestamps e campos auxiliares que não indicam mudança real
    no cenário competitivo, garantindo que persistências sejam acionadas
    apenas quando há alteração relevante.

    Args:
        payload: Dicionário de resumo de comparação. Valores não-dict
            resultam em snapshot vazio (comportamento defensivo).

    Returns:
        Dict contendo apenas os campos de MATERIAL_FIELDS presentes
        no payload. Campos ausentes são omitidos (não incluídos como None).

    Exemplos:
        >>> snap = extract_material_snapshot({
        ...     "monitored_price": 100.0,
        ...     "computed_at": "2026-01-01T00:00:00",  # ignorado
        ...     "competitiveness_status": "urgente",
        ... })
        >>> "computed_at" in snap
        False
        >>> snap["competitiveness_status"]
        'urgente'
    """
    if not isinstance(payload, dict):
        return {}

    return {field: payload.get(field) for field in MATERIAL_FIELDS}

def snapshot_has_changed(
    current: Dict[str, Any],
    previous: Optional[Dict[str, Any]],
) -> bool:
    """ Indica se o snapshot atual difere materialmente do anterior.

    Retorna True em dois casos:
    1. previous é None (nenhum snapshot anterior existe — primeira persistência)
    2. Os campos materiais de current e previous são diferentes

    Args:
        current: Snapshot material extraído do novo resumo calculado.
            Deve ser o resultado de extract_material_snapshot().
        previous: Snapshot material do resumo anterior persistido.
            None indica que não há snapshot anterior (primeira comparação).

    Returns:
        bool: True se deve persistir o novo resumo, False se os dados
            são idênticos e a escrita pode ser evitada.

    Exemplos:
        >>> snapshot_has_changed({"status": "urgente"}, None)
        True
        >>> snapshot_has_changed({"status": "urgente"}, {"status": "urgente"})
        False
        >>> snapshot_has_changed({"status": "urgente"}, {"status": "competitivo"})
        True
    """
    if previous is None:
        return True

    return current != previous
