# Checklist de segurança

- [ ] SECRET_KEY forte e privada em produção.
- [ ] DEBUG=False, HTTPS, cookies Secure, hosts e CSRF configurados.
- [ ] Não aceitar tenant_id de payload como autoridade.
- [ ] Testes negativos de acesso cruzado entre tenants em todas as APIs.
- [ ] Validar tenant de produto, cliente, pedido, reserva e categoria.
- [ ] Rate limit nos endpoints públicos e proteção contra abuso.
- [ ] Token de consulta de pedido aleatório, com expiração/revogação.
- [ ] Não expor dados pessoais no catálogo público.
- [ ] Segredos de WhatsApp e pagamentos fora do repositório.
- [ ] Política de retenção, consentimento e atendimento LGPD.
- [ ] Backups testados e monitoramento de erros.
- [ ] Uploads validados por tipo/tamanho e armazenados com segurança.
