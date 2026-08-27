# Integração CILogon/LSST, SATOSA, COmanage e LDAP

Este documento resume a implementação usada para sincronizar os grupos
recebidos do CILogon/LSST com o COmanage e provisioná-los no LDAP como grupos
POSIX.

## Visão geral

```text
CILogon/LSST
    -> SATOSA
    -> plugin comanage_account_linking
    -> COmanage
    -> fila de provisionamento
    -> LDAP
```

O SATOSA atualiza pessoas, grupos e membros no COmanage. O LDAP Provisioner do
COmanage é o único componente que escreve no LDAP.

## 1. Configuração do COmanage

### Unix Cluster

Em `Configuration -> Clusters`, crie ou selecione o Unix Cluster usado pelo
ambiente. Configure os tipos de identificador usados como:

- UID do usuário;
- nome do grupo;
- GID do grupo.

O ID usado pelo plugin SATOSA é o `unix_cluster_id`, correspondente a
`cm_unix_clusters.id`.

### LDAP Provisioning Target

Em `Configuration -> Provisioning Targets`, configure o LDAP Provisioner com:

- servidor e credenciais LDAP;
- People Base DN;
- Group Base DN;
- Unix Cluster correto;
- object class `posixGroup`;
- atributos `cn`, `gidNumber` e `memberUid`;
- modo `Queue` para a operação normal.

Não use `groupOfNames` nesse target. Esse modelo representa membros por DN,
enquanto a integração precisa de `gidNumber` e `memberUid` para uso em
sistemas Unix/Linux.

### API User

O API User utilizado pelo SATOSA precisa consultar pessoas e identificadores e
gerenciar:

- CoGroups;
- CoGroupMembers;
- UnixClusterGroups.

As credenciais devem permanecer fora do repositório.

### Teste inicial

Antes de integrar o SATOSA:

1. Crie um grupo em `Regular Groups`.
2. Associe-o ao cluster em `Manage Unix Cluster Groups`.
3. Adicione um usuário ativo ao grupo.
4. Execute `Provision` em `Provisioned Services`.
5. Confirme no LDAP a criação do `posixGroup` com GID e membros.

Esse teste confirma que o COmanage, o Unix Cluster e o LDAP Provisioner estão
configurados corretamente.

## 2. Alteração do plugin SATOSA

O plugin já localizava o usuário, criava grupos no COmanage e sincronizava seus
membros. Foi acrescentada a associação automática de cada grupo ao Unix
Cluster.

Essa associação corresponde à ação manual executada em
`Manage Unix Cluster Groups` e é necessária para o provisionamento POSIX.

### Configuração

Foi adicionado `unix_cluster_id` à configuração de cada backend:

```yaml
target_backends:
  - name: "rubin_oidc"
    prefix: "lsst"
    unix_cluster_id: 1
```

O valor deve ser um número inteiro positivo e deve apontar para o Unix Cluster
do ambiente.

### Operação implementada

Para cada grupo recebido do CILogon/LSST, o plugin executa:

```text
localizar ou criar CoGroup
    -> verificar a associação UnixClusterGroup
    -> criar a associação quando ausente
    -> sincronizar CoGroupMembers
```

A associação ao cluster ocorre antes da alteração dos membros. Assim, qualquer
job gerado pelo COmanage encontra o grupo preparado para o provisionamento
POSIX.

A operação é idempotente: uma associação existente não é criada novamente.

### Arquivos alterados

- `satosa/plugins/microservices/comanage_account_linking.yaml.example`;
- `satosa/plugins/microservices/custom/comanage_account_linking/__init__.py`;
- `satosa/plugins/microservices/custom/comanage_account_linking/api.py`;
- `satosa/plugins/microservices/custom/comanage_account_linking/groups.py`;
- `tests/plugins/microservices/test_comanage_posix_groups.py`.

Teste automatizado:

```bash
source pytest-env.sh
pytest -q tests/plugins/microservices/test_comanage_posix_groups.py
```

## 3. Processamento da fila

O provisioning target permanece em `Queue Mode`. As alterações no COmanage
registram jobs, processados pelo comando:

```bash
cd /srv/comanage-registry
/bin/sh lib/Cake/Console/cake job --runqueue --coid 2
```

O wrapper instalado no host é:

```text
/apps/register-dev/comanage-runqueue
```

Ele evita execuções concorrentes e identifica locks órfãos. A cron usa `flock` e executa a cada três minutos:

```cron
*/3 * * * * /bin/flock -n /apps/register-dev/run/comanage-registry-dev-co2.lock /apps/register-dev/comanage-runqueue >> /apps/register-dev/logs/comanage-registry-dev-jobqueue.log 2>&1
```

Em um arquivo de `/etc/cron.d`, deve-se incluir o usuário que executará o
comando. Em `crontab -e`, esse campo não deve ser incluído.

O parâmetro `--coid` limita a execução ao CO, não a um provisioning target
específico.

## 4. Fluxo completo

1. O usuário autentica-se pelo CILogon/LSST.
2. O SATOSA recebe a identidade e os grupos do usuário.
3. O plugin localiza a pessoa no COmanage.
4. Para uma pessoa ativa, o plugin monta os nomes dos grupos com o prefixo do
   backend.
5. Cada grupo é localizado ou criado.
6. Cada grupo é associado ao Unix Cluster.
7. Os membros são sincronizados no COmanage.
8. O COmanage registra os jobs de provisionamento.
9. A cron executa o processador da fila.
10. O LDAP Provisioner cria ou atualiza os `posixGroup`.
11. O LDAP passa a refletir o GID e os membros registrados no COmanage.

Se o usuário ainda não existir ou não estiver ativo, ele segue o fluxo de
registro e aprovação, sem sincronização de grupos nessa autenticação.

O plugin administra somente os grupos pertencentes ao prefixo do backend.

## 5. Validação ponta a ponta

Após autenticar um usuário de teste, confirme:

1. o CoGroup em `Regular Groups`;
2. a associação em `Manage Unix Cluster Groups`;
3. o usuário como membro do grupo;
4. a conclusão dos jobs do COmanage;
5. o `posixGroup` no LDAP.

Exemplo de consulta:

```bash
ldapsearch -LLL -o ldif-wrap=no -x \
  -H 'ldap://SERVIDOR_LDAP' \
  -D 'BIND_DN' \
  -W \
  -b 'ou=groups,dc=linea,dc=org' \
  '(cn=lsst_grupo)' \
  dn objectClass cn gidNumber memberUid
```

Repita o teste adicionando e removendo um usuário do grupo. O atributo
`memberUid` deve acompanhar as alterações após o processamento da fila.

## 6. Implantação em produção

1. Confirme CO ID, Unix Cluster ID, DNs e prefixos do ambiente.
2. Configure o Unix Cluster e os identificadores UID/GID.
3. Configure o LDAP Provisioning Target como `posixGroup`.
4. Valide manualmente o provisionamento de um grupo.
5. Implante o plugin SATOSA atualizado.
6. Configure `unix_cluster_id` no backend.
7. Execute os testes automatizados.
8. Reinicie o SATOSA.
9. Instale o wrapper `comanage-runqueue` e a entrada da cron.
10. Execute uma autenticação de teste.
11. Confirme grupo, associação, membros, jobs e entrada LDAP.
12. Mantenha o target em `Queue Mode` durante a operação normal.

## Observações operacionais

- O plugin sincroniza grupos e membros, mas não exclui o próprio CoGroup.
- Para excluir um grupo administrativamente, use temporariamente o
  `Manual Mode`, remova o grupo e retorne o target ao `Queue Mode`.
- Uma entrada antiga criada como `groupOfNames` deve ser removida e
  reprovisionada como `posixGroup`.
- Se o provedor de identidade continuar enviando um grupo excluído, o plugin
  poderá criá-lo novamente.
