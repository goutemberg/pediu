# Arquitetura do Pediu

## Estilo
Monólito modular Django, API REST versionada, PostgreSQL compartilhado e multi-tenancy por linha (`tenant_id`). Não iniciar com microserviços.

## Multi-tenancy
- `Tenant` representa cada estabelecimento.
- `Membership` associa usuário global a uma empresa e papel.
- Toda entidade comercial deve carregar `tenant_id`.
- Toda consulta administrativa deve partir do tenant resolvido pela associação autenticada, nunca de um `tenant_id` arbitrário enviado pelo cliente.
- Endpoints públicos resolvem a empresa por slug e expõem somente campos públicos.
- Validar que FKs relacionadas pertencem ao mesmo tenant.
- Considerar PostgreSQL RLS como defesa adicional após testes e revisão.

## Domínios
`accounts`, `tenants`, `catalog`, `customers`, `inventory`, `orders`, `notifications`, `subscriptions`, `dashboard`.

## Regras de dependência
- Views/serializers: HTTP e validação de formato.
- Services: casos de uso e transações.
- Models: integridade e relações.
- Selectors (a criar quando necessário): consultas complexas e leitura.
- Integrações externas ficam atrás de adaptadores.

## Pedidos e estoque
Criar pedido deve validar preço no servidor, mínimos e múltiplos, verificar estoque com `select_for_update`, reservar na mesma transação, salvar snapshots de nome/código/unidade/preço e suportar idempotência. Aprovar mantém reserva; rejeitar/cancelar/expirar libera; concluir consome reserva e gera saída física.

## Dinheiro
Usar `DecimalField`, nunca float. O frontend nunca é fonte de preço ou total.

## Arquivos
Em produção usar armazenamento de objetos privado/público conforme política; não depender do disco efêmero do container.
