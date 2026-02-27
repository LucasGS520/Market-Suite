"""Facade de utilitários públicos da feature de comparações.

Organiza exports utilitários por domínio (snapshot, despacho e filtragem)
para simplificar importações e evitar dependência em arquivos concretos.
"""

from market_alert.comparisons.utils.comparison_utils import (
    ComparisonCompetitorEntry,
    FilteredCompetitorsResult,
    LatestSnapshotResult,
    filter_competitors_for_comparison,
    load_latest_snapshot,
    load_monitored_and_competitors,
    should_refresh_competitors_count,
)
from market_alert.comparisons.utils.price_comparator import (
    _parse_force_compare_,
    calculate_discrepancies,
    compare_prices,
    dispatch_comparison_for_scrape_result,
    request_comparison_recompute,
    resolve_recompute_reason,
    schedule_comparison_after_commit,
)
from market_alert.comparisons.utils.snapshot_comparator import (
    extract_material_snapshot,
    snapshot_has_changed,
)

__all__ = [
    "FilteredCompetitorsResult",
    "ComparisonCompetitorEntry",
    "LatestSnapshotResult",
    "load_monitored_and_competitors",
    "load_latest_snapshot",
    "filter_competitors_for_comparison",
    "should_refresh_competitors_count",
    "request_comparison_recompute",
    "resolve_recompute_reason",
    "calculate_discrepancies",
    "compare_prices",
    "dispatch_comparison_for_scrape_result",
    "schedule_comparison_after_commit",
    "_parse_force_compare_",
    "extract_material_snapshot",
    "snapshot_has_changed",
]
