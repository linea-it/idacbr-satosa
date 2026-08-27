# LIneA SATOSA proxy

[Portuguese version](README.pt-BR.md)

[Detailed integration guide (Portuguese)](docs/INTEGRACAO_COMANAGE_SATOSA_LDAP.pt-BR.md)

This repository contains the SATOSA customizations used by LIneA. The main
integration connects CILogon/LSST to COmanage Registry and LDAP, keeping users,
POSIX groups, and group memberships synchronized.

## Flow overview

```text
User
  -> CILogon/LSST
  -> SATOSA
  -> COmanage Registry
  -> provisioning queue
  -> LDAP
```

During authentication:

1. The user authenticates through CILogon/LSST.
2. SATOSA receives the identity and groups provided by the identity provider.
3. The plugin looks up the user in COmanage or starts the registration process
   when necessary.
4. For active users, the plugin creates or locates the received groups.
5. Each group is associated with the configured Unix Cluster.
6. User-to-group memberships are updated in COmanage.
7. COmanage registers the corresponding provisioning jobs.
8. The queue is processed and the LDAP Provisioner updates LDAP.

Each component has a well-defined responsibility:

- **CILogon/LSST:** authenticates the user and provides their groups.
- **SATOSA:** coordinates authentication and runs the synchronization plugin.
- **COmanage:** maintains users, groups, and memberships.
- **LDAP Provisioner:** converts the COmanage state into LDAP entries.
- **Queue processor:** runs the jobs created by COmanage.

## SATOSA plugin change

The plugin already created groups in COmanage and synchronized their members. It
was updated to also associate each group with a Unix Cluster.

This association allows COmanage to manage the group as a POSIX group, generate
its `gidNumber`, and provide the data required by the LDAP Provisioner.

The plugin now follows this sequence:

```text
locate or create the CoGroup
  -> ensure the Unix Cluster association
  -> add or remove members
```

The operation is idempotent: if the association already exists, it is reused.
The association is also established before membership changes, ensuring that
the group is ready for POSIX provisioning.

## Configuration

### SATOSA

Each synchronized backend must specify the Unix Cluster that will receive its
groups:

```yaml
module: comanage_account_linking.COmanageAccountLinkingMicroService
name: COmanageAccountLinking
config:
  api_url: "https://registry.example.org/"
  api_user: "api_username"
  password: "api_password"
  target_backends:
    - name: "rubin_oidc"
      prefix: "lsst"
      unix_cluster_id: 7
  co_id: "2"
```

The `unix_cluster_id` parameter identifies the UnixCluster plugin record in
COmanage (`cm_unix_clusters.id`). The example configuration is available at
`satosa/plugins/microservices/comanage_account_linking.yaml.example`.

### COmanage

The following must be configured in COmanage:

- the Unix Cluster used by the integration;
- the identifier types used for UID, group name, and GID;
- the LDAP Provisioning Target in **Queue Mode**;
- the Group Base DN for the LDAP tree;
- the POSIX classes associated with the Unix Cluster;
- `posixGroup` with the `cn`, `gidNumber`, and `memberUid` attributes.

Changes can generate `CoPerson` and `CoGroup` jobs. Person jobs keep individual
user data up to date, while group jobs maintain the POSIX entry and its member
list. Both are processed by the same provisioning queue.

## Queue processing

COmanage records changes in Queue Mode, and a scheduled process runs the queue.
Inside the container, the base command is:

```bash
cd /srv/comanage-registry
/bin/sh lib/Cake/Console/cake job --runqueue --coid 2
```

In the environment described here, a wrapper on the host runs this command in
the container and writes logs under `/apps/register-dev`. Cron calls the wrapper
every three minutes and uses `flock` to prevent overlapping executions.

```cron
*/3 * * * * /bin/flock -n /apps/register-dev/run/comanage-registry-dev-co2.lock /apps/register-dev/comanage-runqueue >> /apps/register-dev/logs/comanage-registry-dev-jobqueue.log 2>&1
```

## Operation and validation

The provisioning target normally remains in Queue Mode. Group creation and
membership changes are therefore automatically propagated to LDAP.
Administrative operations that should not be propagated can be performed with
the target temporarily set to Manual Mode.

To validate the integration:

1. Authenticate a user who belongs to a test group.
2. Confirm the user and group in COmanage.
3. Confirm that the group is associated with the Unix Cluster.
4. Wait for the queue to be processed.
5. Check the `posixGroup`, `gidNumber`, and `memberUid` values in LDAP.

## Development and testing

Create a virtual environment and install the dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Prepare the local configuration files:

```bash
cp pytest-env.sh.example pytest-env.sh
cp satosa/plugins/microservices/comanage_account_linking.yaml.example \
  satosa/plugins/microservices/comanage_account_linking.yaml
```

Run the tests:

```bash
source pytest-env.sh
pytest --log-file=run-test.log --log-file-level=DEBUG
```

The tests specific to the Unix Cluster association can be run with:

```bash
pytest -q tests/plugins/microservices/test_comanage_posix_groups.py
```
