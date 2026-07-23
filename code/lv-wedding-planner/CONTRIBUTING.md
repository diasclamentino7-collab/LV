# Regras de evolução do LV – Wedding Planner

Estas regras aplicam-se a todas as alterações, incluindo protótipos e módulos
ainda sem interface final.

## Dados e migrações

1. **Nunca apagar dados, tabelas ou colunas.** Não usar `drop_table`,
   `drop_column`, `DELETE`, `TRUNCATE` ou recriação de tabelas em migrações.
2. **Toda a alteração persistente usa Alembic.** A aplicação nunca cria nem
   altera o esquema com `create_all()` ou SQL executado no arranque.
3. **Uma migração aplicada é imutável.** Corrigir um problema criando uma nova
   migração; não editar a que já chegou a outro ambiente.
4. **Rever migrações autogeradas.** `--autogenerate` sugere alterações, mas
   nunca substitui a revisão humana.
5. **Fazer backup antes de produção.** Validar `alembic upgrade head` numa
   cópia representativa da base de dados antes de cada lançamento.

## Compatibilidade sem interrupções

Uma alteração incompatível segue sempre o ciclo **expandir, migrar,
compatibilizar, retirar**:

1. Adicionar estruturas novas de forma opcional e não destrutiva.
2. Preencher dados novos por migração ou processo seguro, mantendo os antigos.
3. Fazer serviços e interfaces aceitarem os formatos antigo e novo.
4. Só retirar código ou campos antigos numa versão futura, depois de uma
   migração de dados explicitamente aprovada. A remoção física de dados não é
   permitida sem uma decisão de produto e um plano de retenção separado.

Durante o desenvolvimento, cada entrega deve manter as páginas, rotas e APIs
já publicadas operacionais. Uma funcionalidade incompleta usa estado vazio ou
feature flag; nunca bloqueia o uso das áreas existentes.

## Módulos e qualidade

- Um domínio vive em `app/modules/<dominio>/` e é dono das suas rotas, schemas,
  serviços, repositórios e modelos.
- Dependências entre módulos passam por contratos pequenos e explícitos; não
  aceder diretamente às tabelas internas de outro módulo.
- Routes tratam HTTP, services tratam regras de negócio e repositories tratam
  persistência. Models não contêm lógica de interface.
- Código novo segue PEP 8 e passa `ruff check .` e `pytest`.
- Cada alteração de comportamento requer testes, incluindo cenários de dados
  existentes quando houver migração.
