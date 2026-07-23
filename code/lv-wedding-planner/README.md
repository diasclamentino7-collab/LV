# LV – Wedding Planner

Fundação profissional e modular para uma aplicação de organização de
casamentos. Esta primeira entrega não inclui funcionalidades de negócio: deixa
uma base segura para as acrescentar ao longo dos anos.

## Arquitetura

- **FastAPI + Jinja2** para API e interface web.
- **SQLAlchemy 2** para persistência, com SQLite local e suporte PostgreSQL via URL.
- **Alembic** como única via para mudanças no esquema de dados.
- **Módulos isolados** em `app/modules/<dominio>/`; cada domínio pode ter os seus
  próprios models, schemas, repositories, services e routes.
- Camadas partilhadas em `app/models`, `app/schemas`, `app/repositories`,
  `app/services` e `app/routes`.

```text
app/          aplicação, camadas e recursos web
migrations/   histórico Alembic
uploads/      ficheiros enviados (fora do Git)
backups/      cópias locais (fora do Git)
data/         SQLite local (fora do Git)
tests/        testes automatizados
```

## Instalação

Requer Python 3.13 ou superior. Em PowerShell:

```powershell
Set-Location C:\Users\diasc\code\lv-wedding-planner
.\scripts\setup.ps1
```

Este comando cria `.venv`, instala as dependências, cria o `.env` a partir do
exemplo e aplica as migrações. O VS Code usa automaticamente
`.venv\Scripts\python.exe` e ativa esse ambiente nos terminais integrados.

## Executar

```powershell
Set-Location C:\Users\diasc\code\lv-wedding-planner
.\scripts\run.ps1
```

Abra `http://127.0.0.1:8000`; OpenAPI fica em `/docs` e a verificação de estado
em `/api/health`.

## Áreas preparadas

As áreas de interface já possuem rotas, mas não implementam operações nem
persistência nesta fase:

| Área | Rota |
| --- | --- |
| Dashboard | `/dashboard` |
| Checklist | `/checklist` |
| Convidados | `/guests` |
| Plano de Mesas | `/table-plan` |
| Orçamento | `/budget` |
| Cronograma | `/timeline` |
| Fornecedores | `/vendors` |
| Cerimónia | `/ceremony` |
| Receção | `/reception` |
| Processo Legal | `/legal-process` |
| Roupa | `/attire` |
| Lua de Mel | `/honeymoon` |
| Casa | `/home` |
| Presentes | `/gifts` |
| Documentos | `/documents` |
| Configurações | `/settings` |

## Migrações e preservação de dados

Nunca use `Base.metadata.create_all()` na aplicação. Ao adicionar ou alterar um
modelo, importe-o em `app/models/__init__.py` e crie uma migração nova:

```powershell
alembic revision --autogenerate -m "add guest module"
alembic upgrade head
```

Não edite migrações já aplicadas noutros ambientes. Para mudanças complexas,
teste primeiro numa cópia da base de dados e acrescente uma nova migração que
preserve ou transforme os dados existentes.

Antes de abrir uma alteração, confirme que não foi introduzida uma operação
destrutiva:

```powershell
python scripts/check_migrations.py
```

As regras completas de retenção de dados, compatibilidade e independência dos
módulos estão em [CONTRIBUTING.md](CONTRIBUTING.md). Em resumo: expandir o
esquema, migrar dados, aceitar temporariamente as versões antiga e nova e só
então retirar código obsoleto numa versão posterior.

## PostgreSQL

```powershell
python -m pip install -e ".[postgres]"
```

No `.env`, substitua `LV_DATABASE_URL` por:

```env
LV_DATABASE_URL=postgresql+psycopg://utilizador:palavra-passe@localhost:5432/lv_wedding_planner
```

Depois execute `alembic upgrade head`. A migração de dados de SQLite para
PostgreSQL deve ser planeada separadamente.

## Produção e PWA

O projeto inclui `Dockerfile`, `docker-compose.yml`, manifest PWA e service
worker. Para produção, copie `.env.production.example` para `.env.production`,
substitua todas as credenciais e execute
`docker compose --env-file .env.production up -d --build`. O Caddy incluído
obtém e renova HTTPS automaticamente quando o domínio configurado em
`CADDY_DOMAIN` já aponta para o servidor. Defina também
`LV_SESSION_HTTPS_ONLY=true` e os domínios em `LV_ALLOWED_HOSTS`.

Para SQLite local, crie um backup agendado com:

```powershell
.\.venv\Scripts\python.exe scripts\backup_database.py
```

Em PostgreSQL, agende `pg_dump` no servidor e mantenha cópias fora do volume
principal. Teste periodicamente a recuperação numa base de dados separada.

## Publicação gratuita: Render + Neon

Esta é a opção recomendada para usar a aplicação no telemóvel sem comprar
domínio nem manter um computador ligado. O Render fornece um subdomínio
`onrender.com`; o Neon fornece PostgreSQL externo persistente. Os dois planos
gratuitos têm limites e o serviço web gratuito pode demorar alguns segundos a
acordar depois de inatividade.

1. Crie gratuitamente uma base em [Neon](https://neon.com/) e copie a
   connection string do painel **Connect**. Converta o início de
   `postgresql://` para `postgresql+psycopg://`.
2. Publique este projeto num repositório privado GitHub. Nunca publique `.env`
   nem a URL da base de dados.
3. Crie uma conta em [Render](https://render.com/), escolha **New → Blueprint**
   e selecione o repositório. O ficheiro `render.yaml` cria o serviço Docker
   gratuito.
4. No Render, em **Environment**, defina `LV_DATABASE_URL` com a URL do Neon.
   Se usar caracteres reservados na password (`@`, `:`, `/`), codifique-os na
   URL. O Blueprint já permite os subdomínios `onrender.com`; ao ligar um
   domínio próprio no futuro, acrescente-o a `LV_ALLOWED_HOSTS`.
5. Faça o primeiro deploy. O contentor aplica `alembic upgrade head` antes de
   iniciar a aplicação. Abra o URL `https://<nome>.onrender.com/setup` para
   criar os dois utilizadores.
6. No Android, use Chrome → menu → **Instalar aplicação**. No iPhone, abra no
   Safari → Partilhar → **Adicionar ao ecrã principal**.

As atualizações futuras são feitas por `git push`: o Render volta a construir a
imagem e executa as novas migrações Alembic. As tabelas e os dados ficam no
Neon, não no contentor temporário do Render.

### Backups gratuitos

O Neon gratuito oferece uma janela limitada de restauro. Para cópias próprias,
execute periodicamente `pg_dump` a partir de um computador seguro contra a URL
de ligação do Neon e guarde o ficheiro fora do repositório. Nunca use uma
migração destrutiva para recuperar espaço.

## Qualidade

```powershell
pytest
ruff check .
python scripts/check_migrations.py
```
