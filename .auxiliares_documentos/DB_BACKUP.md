# Backup e Restauração do Banco (Postgres)

Este guia descreve como criar dumps (backup) e restaurar o banco PostgreSQL usado pelo projeto.

- Serviço PostgreSQL no compose: `db` (ver `docker-compose.yml`).
- Backups são gravados na pasta `backups/` por padrão.

Pré-requisitos
- `docker` e `docker-compose` (ou `docker compose`) instalados e funcionando.
- `python` 3.8+ para os scripts auxiliares (os wrappers `sh`/`ps1` chamam os scripts Python).
- Variáveis de ambiente usadas pelo compose: se necessário, garanta que `POSTGRES_PASSWORD` esteja disponível no ambiente quando executar os scripts (os scripts tentam respeitar `POSTGRES_PASSWORD`, `POSTGRES_USER` e `POSTGRES_DB`).

Criar backup

Pelo Python (cross-platform):

```bash
python scripts/backup_db.py --compress
```

Wrapper (Linux/macOS):

```bash
./scripts/backup_db.sh --compress
```

Wrapper (Windows PowerShell):

```powershell
.\scripts\backup_db.ps1 -Compress
```

Parâmetros úteis
- `--file <path>`: salva em um arquivo específico.
- `--compress` / `-z`: comprime o dump com gzip (.gz).
- `--container <name>`: caso seu serviço Postgres não se chame `db` no `docker-compose.yml`.

Restaurar backup

Exemplo (arquivo .sql ou .sql.gz):

```bash
python scripts/restore_db.py --file backups/backup_20250101_123456Z.sql.gz
```

Wrappers:

```bash
./scripts/restore_db.sh --file backups/backup_....sql.gz
# PowerShell
.\scripts\restore_db.ps1 -File backups\backup_....sql.gz
```

Observações e segurança
- Recomenda-se parar os serviços da aplicação (`market_alert`, workers) antes de restaurar para evitar inconsistências.
- Os scripts tentam usar `POSTGRES_PASSWORD` do ambiente para autenticação via variável `PGPASSWORD`.
- Guarde os arquivos de backup em local seguro (não commite em repositório).

Se quiser, posso também:
- Adicionar uma entrada ao `README.md` com link para este guia.
- Gerar um script que envie os backups para um storage remoto (S3, Azure, Google Cloud).
