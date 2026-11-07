# Registros de decisões arquiteturais (ADR)

## ADR-001 — Monólito modular
Escolha: Django modular em uma aplicação implantável. Motivo: menor custo operacional e domínio ainda em validação.

## ADR-002 — Banco compartilhado multi-tenant
Escolha: PostgreSQL compartilhado com `tenant_id`, constraints e escopo obrigatório. Motivo: simplicidade operacional para primeiros clientes. Revisar apenas se requisitos de isolamento/regulação exigirem bancos separados.

## ADR-003 — Usuário global e Membership
Escolha: usuário pode participar de várias empresas; papel pertence à associação.

## ADR-004 — Cliente visitante
Escolha: catálogo público e pedido sem conta. Histórico vinculado ao telefone dentro de cada empresa; consulta pública exige token aleatório não enumerável.

## ADR-005 — Aprovação manual e reserva
Escolha: pedido entra pendente e reserva estoque atomicamente com prazo configurável.
