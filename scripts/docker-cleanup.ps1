# docker-cleanup.ps1
# Limpa volumes orfaos, imagens nao usadas e cache de build do Docker.
# Uso: .\scripts\docker-cleanup.ps1

Write-Host "Limpando volumes orfaos..." -ForegroundColor Cyan
docker volume prune -f

Write-Host "Limpando imagens nao usadas..." -ForegroundColor Cyan
docker image prune -a -f

Write-Host "Limpando build cache..." -ForegroundColor Cyan
docker builder prune -f

Write-Host ""
Write-Host "Espaco atual apos limpeza:" -ForegroundColor Green
docker system df

Write-Host ""
Write-Host "Cleanup concluido." -ForegroundColor Green
