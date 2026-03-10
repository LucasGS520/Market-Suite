""" Processo standalone do coletor contínuo de monitorados.

Este pacote contém toda a lógica do loop contínuo de coleta,
extraída do Celery para permitir evolução independente e futura
reimplementação em Go/Rust.

Módulos:
    manager           — Ciclo de vida e loop principal
    dispatcher        — Despacho de tasks e decisões de reenqueue
    callbacks         — Callbacks pós-coleta (sucesso/erro)
    queue             — Abstração de domínio sobre a fila Redis
    reconciliation    — Sincronização DB ↔ fila Redis
    services_priority_queue — Primitivas Redis Sorted Set
    main              — Entry point standalone

Uso standalone::

    cd backend && python -m market_continuous.main
"""
