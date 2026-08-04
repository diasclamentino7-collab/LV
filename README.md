# LV – Wedding Planner

Aplicação profissional e modular para planear um casamento em conjunto. Inclui
autenticação, dashboard, CRUD persistente, orçamento, convidados, tarefas,
atividade, comunicação, moodboard, configurações avançadas e instalação PWA.

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

## Áreas da aplicação

| Área | Rota |
| --- | --- |
| Dashboard | `/dashboard` |
| Checklist | `/checklist` |
| Convidados | `/guests` |
| Plano de Mesas | `/table-plan` |
| Orçamento | `/budget` |
| Cronograma | `/timeline` |
| Fornecedores | `/vendors` |
| Pagamentos | `/payments` |
| Despesas | `/expenses` |
| Salão do Reino · Cerimónia | `/kingdom-hall` |
| Copo de Água · Festa | `/reception` |
| Processo Legal | `/legal-process` |
| Roupa | `/attire` |
| Lua de Mel | `/honeymoon` |
| Casa | `/home` |
| Presentes | `/gifts` |
| Documentos | `/documents` |
| Moodboard | `/moodboard` |
| Comunicação | `/communication` |
| Histórico de atividade | `/activity` |
| Todos os eliminados | `/deleted` |
| Configurações | `/settings` |

O **Plano de Mesas** apresenta uma planta visual das mesas, lugares ocupados e
livres, convidados atribuídos e convidados ainda sem mesa. As atribuições podem
ser alteradas diretamente no mapa e ficam imediatamente guardadas na base de
dados, com controlo de concorrência entre os dois utilizadores. As fichas das
mesas continuam disponíveis para definir nome, capacidade, forma, zona e notas;
uma atribuição existente nunca desaparece se a ficha da mesa ainda não tiver
sido criada.

As rotas históricas `/ceremony` e `/quinta` são mantidas por compatibilidade e
encaminham para os módulos consolidados sem alterar ou apagar os registos
existentes.

## Configurações avançadas

Em `/settings` é possível gerir, por secções independentes:

- identidade do projeto, nomes do casal e logótipo por URL;
- data e hora, fuso horário, estilo, locais e objetivo de convidados;
- orçamento, moeda e percentagem de alerta;
- cores aplicadas em toda a interface;
- responsável e prioridade predefinidos, lembretes e blocos do dashboard;
- intensidade de movimento: completa, reduzida ou sem animações;
- colaboradores, alteração de password, instalação PWA e exportações PDF/JSON;
- proteção contra alterações concorrentes, aviso de moeda sem conversão e
  confirmação antes de abandonar formulários por guardar.

Cada gravação fica registada no histórico de atividade. Um controlo de versão
impede que um formulário antigo substitua silenciosamente alterações feitas
pela outra pessoa. O relatório legível em `/settings/export.pdf` e os PDFs de
cada módulo em `/exports/<modulo>.pdf` excluem passwords e dados internos de
autenticação. A cópia técnica JSON anterior continua disponível em
`/settings/export` para recuperação e compatibilidade.

Os registos eliminados ficam inicialmente recuperáveis. Em `/deleted`, ou na
vista de eliminados de cada módulo, podem ser recuperados ou removidos
definitivamente da interface após escrever `APAGAR`. A remoção definitiva cria
uma marca e um snapshot técnico de auditoria, sem apagar fisicamente a linha ou
quebrar despesas, pagamentos e outras relações existentes. Identificadores
únicos de negócio, como o nome de uma categoria do orçamento, são libertados
nessa operação e podem ser utilizados imediatamente num novo registo.

O histórico em `/activity` identifica utilizador, data/hora, módulo, ação e
descrição, com filtros combináveis. É apenas de leitura e mostra até 250
resultados por pesquisa.

Todos os formulários que alteram dados utilizam um token CSRF associado à
sessão. As passwords são guardadas apenas como hashes e as respostas incluem
políticas de segurança para conteúdo, frames, permissões e HTTPS.
Cinco tentativas de login sem sucesso bloqueiam temporariamente a conta. Alterar
a password revoga também as sessões anteriores, incluindo noutros dispositivos.

## Motion design e utilização diária

A interface inclui um sistema central, leve e sem bibliotecas externas para
transições de página, entrada progressiva de listas, números, barras de
progresso, cartões com profundidade subtil, microinterações, modais e mensagens.
Os efeitos utilizam `transform`, `opacity`, `requestAnimationFrame` e
`IntersectionObserver`; o parallax é automaticamente desligado em ecrãs táteis,
modo de poupança de dados e dispositivos mais limitados.

A preferência **Reduzir movimento** do sistema operativo tem sempre prioridade.
Mesmo que seja escolhido movimento completo nas Configurações, a aplicação
reduz os efeitos quando `prefers-reduced-motion` está ativo. Com **Sem
animações**, todas as páginas e ações continuam completamente funcionais.

A lupa do cabeçalho abre uma pesquisa global instantânea. Também pode ser
aberta com `Ctrl + K` no Windows ou `⌘ + K` no macOS. Permite encontrar áreas,
abrir formulários frequentes e navegar apenas com as setas e `Enter`, sem fazer
pedidos ao servidor enquanto se pesquisa.

A página **Convidados** funciona como uma folha de cálculo colaborativa:
edição direta nas células, gravação automática na base de dados, linha de
adição rápida, pesquisa e filtros dinâmicos, ordenação, seleção múltipla,
ações em grupo e vista compacta. No telemóvel, cada linha transforma-se num
cartão editável. A lista sincroniza alterações feitas noutro dispositivo e
protege uma edição em curso contra substituições silenciosas.

As restantes listas usam um workspace comum com pesquisa instantânea, ordenação
por coluna, contagem visível, seleção por teclado e densidade confortável ou
compacta. O HTML tradicional continua a funcionar sem JavaScript. Os
formulários partilham validação inline, progresso de preenchimento, aviso de
alterações por guardar, textareas ajustáveis e o atalho Ctrl/Cmd + S. O
Histórico de atividade e Todos os eliminados também permitem pesquisar e
ordenar localmente os resultados já carregados, sem pedidos adicionais nem
atrasos de navegação.

O bloco **LV – Wedding Planner** regressa imediatamente ao Dashboard e a nova
página recebe apenas uma entrada curta e subtil, sem temporizadores antes da
navegação. Se o Dashboard já estiver aberto, não há reload: apenas uma
confirmação visual no próprio logótipo. Formulários alterados pedem confirmação
antes de qualquer navegação e o efeito é automaticamente reduzido no telemóvel
ou quando `prefers-reduced-motion` está ativo.

O Dashboard consulta periodicamente um resumo autenticado e sem cache. Quando
outra pessoa altera convidados, checklist, orçamento ou data do casamento,
apenas os valores afetados são atualizados e destacados; não são usados valores
fictícios e a página não precisa de ser recarregada. A contagem decrescente é
calculada no fuso horário definido nas Configurações e atualiza também os
segundos.

A visão de Orçamento usa a mesma fonte financeira do Dashboard e mostra total,
despesas atuais, restante, limites planeados e utilização por categoria. Os
gráficos são construídos apenas com despesas persistidas. A página reconcilia
alterações a cada 12 segundos e também ao regressar ao separador; separadores
abertos no mesmo dispositivo recebem ainda um sinal imediato, sem substituir a
base de dados por armazenamento local.

O ícone superior direito abre o Centro de Comunicação como painel lateral. A
pesquisa e a criação rápida de notas, ideias, decisões, lembretes e tarefas
guardam diretamente na base de dados, com autoria e atividade. A página completa
continua disponível em `/communication`.

O Moodboard dispõe de galeria, favoritos, pré-visualização acessível e da vista
**Mesa de Inspiração**. Posições, rotações e camadas são persistidas numa tabela
própria; podem ser alteradas com rato, toque ou teclado e nunca ficam apenas na
memória do navegador.

## Assistente de IA

O ícone com o símbolo ✨ no cabeçalho abre um painel lateral com um assistente
conversacional, com separadores para escolher entre ChatGPT, Claude e Gemini;
cada separador mantém a sua própria conversa, guardada na base de dados e
partilhada pelos dois utilizadores. Antes de responder, o assistente recebe
um resumo apenas de leitura do casamento (orçamento, convidados e tarefas
atuais) — nunca altera dados sozinho.

Cada assistente precisa da respetiva chave de API, definida no `.env`:

```env
LV_OPENAI_API_KEY=
LV_OPENAI_MODEL=gpt-4o-mini
LV_ANTHROPIC_API_KEY=
LV_ANTHROPIC_MODEL=claude-opus-5
LV_GEMINI_API_KEY=
LV_GEMINI_MODEL=gemini-2.0-flash
```

Sem a chave correspondente, esse separador informa que ainda não está
configurado; os restantes continuam a funcionar normalmente. As chaves nunca
chegam ao navegador — todos os pedidos são feitos pelo servidor.

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

O verificador recusa remoções de tabelas/colunas, renomeações destrutivas e SQL
com `DROP`, `TRUNCATE` ou `DELETE FROM`. As migrações de produção são sempre
aditivas e os `downgrade` não apagam dados.

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
Em produção, a aplicação recusa arrancar com SQLite, uma chave de sessão fraca,
cookies sem HTTPS ou um `LV_SETUP_TOKEN` com menos de 32 caracteres. Isto evita
publicar acidentalmente uma instalação insegura.

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
   connection string do painel **Connect**. Pode colá-la com `postgresql://`;
   a aplicação seleciona automaticamente o driver `psycopg` 3.
2. Publique este projeto num repositório privado GitHub. Nunca publique `.env`
   nem a URL da base de dados.
3. Crie uma conta em [Render](https://render.com/), escolha **New → Blueprint**
   e selecione o repositório. O ficheiro `render.yaml` cria o serviço Docker
   gratuito.
4. No Render, em **Environment**, defina `LV_DATABASE_URL` com a URL do Neon.
   Se usar caracteres reservados na password (`@`, `:`, `/`), codifique-os na
   URL. O Blueprint já permite os subdomínios `onrender.com`; ao ligar um
   domínio próprio no futuro, acrescente-o a `LV_ALLOWED_HOSTS`. Defina também
   `LV_SETUP_TOKEN` com um valor privado de pelo menos 32 caracteres que consiga
   copiar no passo seguinte. O Blueprint gera um valor seguro automaticamente,
   mas pode substituí-lo por outro valor forte conhecido por si.
5. Faça o primeiro deploy. O contentor aplica `alembic upgrade head` antes de
   iniciar a aplicação. Abra o URL `https://<nome>.onrender.com/setup`, introduza
   o `LV_SETUP_TOKEN` e crie os dois utilizadores. Depois de existirem contas,
   essa página encaminha sempre para o login.
6. No Android, use Chrome → menu → **Instalar aplicação**. No iPhone, abra no
   Safari → Partilhar → **Adicionar ao ecrã principal**.

As atualizações futuras são feitas por `git push`: o Render volta a construir a
imagem e executa as novas migrações Alembic. As tabelas e os dados ficam no
Neon, não no contentor temporário do Render.

O endpoint `/api/health` só responde como saudável quando a aplicação consegue
consultar realmente a base de dados; o Render não envia tráfego para uma
instância sem ligação ao Neon.

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
