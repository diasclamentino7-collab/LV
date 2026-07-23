# Módulos de domínio

Cada funcionalidade futura deve ter um pacote próprio, por exemplo
`app/modules/guests/` ou `app/modules/budget/`. Cada pacote pode conter as suas
rotas, schemas, serviços, repositórios e modelos.

Qualquer mudança persistente exige uma nova migração Alembic. Nunca editar uma
migração já aplicada: criar sempre uma migração adicional.
