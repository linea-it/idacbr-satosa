# LIneA SATOSA proxy

This repository contains some Satosa customizations for LIneA's needs (mainly in plugins) and files/structures that work as a kind of Satosa backup in our infrastructure, obviously without sensitive information.

## COmanage Account Linking Plugin

This plugin enables account linking between identity providers and COmanage Registry through SATOSA proxy.

### Installation

1. Add the plugin files to your SATOSA installation:

```bash
cp -r satosa/plugins/microservices/custom/comanage_account_linking/ /path/to/satosa/plugins/microservices/
```

### Configuration

1. Add the microservice configuration to your SATOSA proxy configuration file:

```yaml:proxy_conf.yaml
MICRO_SERVICES:
  - module: satosa.micro_services.comanage_account_linking.COmanageAccountLinkingMicroService
    name: COmanageAccountLinking
    config:
      api_url: "https://registry.example.org/api"
      api_user: "api_username"
      password: "api_password"
      target_backends:
        - name: "oidc"
        - name: "saml2"
          prefix: "custom_saml2"
     co_id: "2"
```

#### Configuration Parameters

- `api_url`: COmanage Registry API base URL
- `api_user`: COmanage API username
- `password`: COmanage API password
- `target_backends`: List of SATOSA backends to enable account linking
- `co_id`: COmanage Organization ID

### Usage

The plugin will:
1. Automatically create/retrieve COmanage users during authentication
2. Manage group memberships between identity providers and COmanage
3. Handle account linking across configured backends

#### Error Handling

The plugin includes several error classes for specific scenarios:
- `COmanageAPIError`: API communication issues
- `COmanageUserError`: User-related errors
- `COmanageGroupsError`: Group management errors
- `COmanageAccountLinkingError`: General account linking errors

### Development

Create a virtualenv:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt`
```

Copy and edit the files and fill in the values:
```bash
cp pytest-env.sh.example pytest-env.sh
cp satosa/plugins/microservices/comanage_account_linking.yaml.example satosa/plugins/microservices/comanage_account_linking.yaml
```

#### Run tests

```bash
source pytest-env.sh
pytest --log-file=run-test.log --log-file-level=DEBUG
```


