# Segurança e endurecimento do pediu.

Este documento descreve os controles aplicados no código e as ações operacionais necessárias antes de produção. A revisão não substitui teste de invasão nem auditoria da infraestrutura publicada.

## 1. Papéis e autorização

As views do painel usam `apps.core.permissions.require_roles`, que valida a associação ativa do usuário à empresa selecionada na sessão.

| Ação | OWNER | MANAGER | STAFF |
|---|---:|---:|---:|
| Dashboard e consulta de pedidos | Sim | Sim | Sim |
| Aprovar, rejeitar, cancelar e atualizar pedidos | Sim | Sim | Sim |
| Cadastrar e editar produtos | Sim | Sim | Não |
| Cadastrar e editar categorias | Sim | Sim | Não |
| Ajustar estoque pelo formulário de produto | Sim | Sim | Não |
| Ativar/desativar produtos e categorias | Sim | Não | Não |
| Gerenciar membros e permissões | Somente proprietário | Não | Não |
| Configurações gerais da loja | Somente proprietário | Não | Não |

A tabela é a política pretendida. Funcionalidades de gerenciamento de membros/configurações ainda devem passar pela mesma camada quando forem implementadas.

## 2. Isolamento entre empresas

- As views de catálogo consultam objetos pelo tenant ativo.
- As views de pedidos restringem a consulta ao tenant ativo.
- A troca de empresa valida uma Membership ativa do próprio usuário.
- A camada `require_roles` consulta a Membership para a empresa ativa, não apenas o papel global do usuário.

Antes de publicar, execute testes negativos para cada endpoint: usuário da loja A tenta ler, alterar, excluir ou acionar IDs pertencentes à loja B. O resultado esperado é 404 ou 403, sem revelar dados da outra empresa.

## 3. Limitação de tentativas

O pacote `django-ratelimit` limita POSTs por IP:

- Login: 10 tentativas por minuto.
- Cadastro: 5 tentativas por minuto.
- Checkout: 15 tentativas por minuto.

Em desenvolvimento, o cache local em memória é suficiente. Em produção com mais de um processo/instância, configure `REDIS_URL` para que os contadores sejam compartilhados. Sem cache compartilhado, o limite pode ser aplicado separadamente em cada processo.

## 4. HTTPS e cookies

O módulo `config.settings.production` ativa redirecionamento HTTPS, cookies Secure, proteção de conteúdo, `X-Frame-Options` e suporte a HSTS configurável. Defina `ALLOWED_HOSTS` com os hosts reais. HSTS começa desabilitado (`SECURE_HSTS_SECONDS=0`) de propósito: habilite gradualmente depois de confirmar HTTPS e subdomínios.

Variáveis recomendadas:

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DEBUG=0
SECRET_KEY=<segredo-aleatorio-forte>
ALLOWED_HOSTS=seudominio.com,www.seudominio.com
CSRF_TRUSTED_ORIGINS=https://seudominio.com,https://www.seudominio.com
SECURE_HSTS_SECONDS=0
REDIS_URL=redis://<host-privado>:6379/1
```

Não use a chave ou senhas de desenvolvimento em produção. Não envie `.env` para Git, imagens públicas ou pacotes compartilhados.

## 5. Banco de dados e Docker

A porta do PostgreSQL no Compose foi limitada a `127.0.0.1`, mantendo o acesso local de desenvolvimento sem publicar o banco em todas as interfaces. Em produção, prefira rede privada e não publique a porta do banco.

- Use senha exclusiva e forte para PostgreSQL.
- Restrinja firewall e usuários do banco.
- Faça backup automático e criptografado.
- Teste restauração em ambiente separado regularmente.
- Nunca remova o volume `postgres_data` para resolver problemas de aplicação.

## 6. Integridade e concorrência de pedidos

As transições `approved -> preparing` e `preparing -> ready` agora passam por `transition_order`, que bloqueia o pedido em transação e valida o status esperado. As operações de aprovação, rejeição, cancelamento e conclusão continuam usando os serviços transacionais existentes.

## 7. Privacidade e LGPD

Pedidos guardam nome, telefone, endereço e observações. Antes da operação comercial:

- publique política de privacidade e informe finalidade do tratamento;
- colete somente dados necessários para cumprir o pedido;
- defina prazo de retenção e procedimento de descarte/anonimização;
- restrinja acesso aos dados de clientes por papel;
- registre incidentes e mantenha processo de atendimento aos direitos dos titulares;
- avalie contratos com hospedagem, e-mail, analytics e demais operadores.

## 8. Logs e monitoramento

Configure logs centralizados sem registrar senhas, tokens, cookies, conteúdo integral de formulários ou dados pessoais desnecessários. Monitore falhas de autenticação, erros 403/404/500, indisponibilidade, crescimento de pedidos e falhas do expirer. Defina alertas e responsável pela resposta a incidentes.

## 9. Verificações antes de produção

- [ ] `python manage.py check --deploy` no ambiente de produção.
- [ ] `DEBUG=0`, `ALLOWED_HOSTS` restrito e `SECRET_KEY` forte.
- [ ] HTTPS testado; depois habilitar HSTS progressivamente.
- [ ] Redis compartilhado configurado para rate limiting em múltiplas instâncias.
- [ ] PostgreSQL sem exposição pública e com backup/restauração testados.
- [ ] Testes de acesso cruzado entre tenants em todas as rotas autenticadas e APIs.
- [ ] Revisão de permissões do Django Admin e de superusuários.
- [ ] Inventário de dependências e verificação de CVEs antes de cada release.
- [ ] Política de privacidade, retenção e resposta a incidentes definida.
- [ ] Teste de carga e teste de concorrência em pedidos/estoque.

## Escopo

As alterações deste pacote são endurecimento de código e documentação. Não foram testadas contra o ambiente publicado, não validam a configuração real do provedor de hospedagem e não constituem certificação de segurança.
