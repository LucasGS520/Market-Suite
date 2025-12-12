from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from market_alert.core.config_alert import settings
from market_alert.tasks import recheck_scheduler_task


class DummySession:
    """Sessão simulada para registrar commits durante os testes."""

    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


def test_schedule_rechecks_updates_window_and_enqueues(monkeypatch):
    """Rechecagens vencidas devem ser reagendadas e enfileiradas com jitter."""

    reference = datetime(2024, 1, 10, 12, 0, tzinfo=timezone.utc)
    monitored = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        product_url="http://example.com/produto",
        name_identification="Produto",
        next_check_at=reference - timedelta(seconds=5),
        check_interval=45,
    )

    scheduled_payloads: list[tuple[dict[str, str], float]] = []
    fake_db = DummySession()

    monkeypatch.setattr(
        recheck_scheduler_task, "_hydrate_missing_next_check", lambda db, ref, logger_bound=None: 0
    )
    monkeypatch.setattr(
        recheck_scheduler_task, "_list_due_monitored", lambda db, ref: [monitored]
    )

    def fake_enqueue(payload: dict[str, str], *, countdown: float | None = None) -> None:
        scheduled_payloads.append((payload, countdown or 0.0))

    dispatched = recheck_scheduler_task.schedule_rechecks(
        fake_db,
        now=reference,
        enqueue_callable=fake_enqueue,
    )

    assert dispatched == 1
    assert fake_db.commits == 1
    assert scheduled_payloads[0][0]["monitored_id"] == str(monitored.id)
    assert 0.0 <= scheduled_payloads[0][1] <= settings.RECHECK_ENQUEUE_JITTER_SECONDS
    assert monitored.next_check_at == reference + timedelta(seconds=45)


def test_schedule_rechecks_honors_suspension(monkeypatch):
    """Quando o scraping estiver suspenso nada deve ser enfileirado."""

    reference = datetime(2024, 1, 10, 12, 0, tzinfo=timezone.utc)
    fake_db = DummySession()

    monkeypatch.setattr(recheck_scheduler_task, "is_scraping_suspended", lambda: True)
    dispatched = recheck_scheduler_task.schedule_rechecks(fake_db, now=reference)

    assert dispatched == 0
    assert fake_db.commits == 0


def test_schedule_rechecks_returns_zero_without_candidates(monkeypatch):
    """Sem monitorados vencidos o agendador deve retornar zero rapidamente."""

    reference = datetime(2024, 1, 10, 12, 0, tzinfo=timezone.utc)
    fake_db = DummySession()

    monkeypatch.setattr(recheck_scheduler_task, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(
        recheck_scheduler_task, "_hydrate_missing_next_check", lambda db, ref, logger_bound=None: 0
    )
    monkeypatch.setattr(recheck_scheduler_task, "_list_due_monitored", lambda db, ref: [])

    dispatched = recheck_scheduler_task.schedule_rechecks(fake_db, now=reference)

    assert dispatched == 0
    assert fake_db.commits == 0