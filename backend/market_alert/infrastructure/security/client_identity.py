""" Resolução centralizada do IP real do cliente """

from fastapi import Request


def resolve_client_ip(request: Request) -> str:
    """
    Retorna o IP real do cliente a partir do request.

    Prioridade:
    1. X-Real-IP  — definido pelo Nginx como $remote_addr (origem confiável)
    2. X-Forwarded-For — primeiro IP da cadeia (fallback)
    3. request.client.host — resolvido pelo uvicorn via --proxy-headers (fallback)
    4. "unknown" — quando nenhuma fonte está disponível
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    if request.client:
        return request.client.host

    return "unknown"
