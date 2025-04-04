# SATOSA
LIneA SATOSA proxy configuration and documentation

## COmanage Account Linking Plugin

This plugin enables account linking between identity providers and COmanage Registry through SATOSA proxy.

## Installation

1. Add the plugin files to your SATOSA installation:

```bash
cp plugins/microservices/comanage_account_linking.py /path/to/satosa/plugins/microservices/
```

## Configuration

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

### Configuration Parameters

- `api_url`: COmanage Registry API base URL
- `api_user`: COmanage API username
- `password`: COmanage API password
- `target_backends`: List of SATOSA backends to enable account linking
- `co_id`: COmanage Organization ID

## Usage

The plugin will:
1. Automatically create/retrieve COmanage users during authentication
2. Manage group memberships between identity providers and COmanage
3. Handle account linking across configured backends

## Error Handling

The plugin includes several error classes for specific scenarios:
- `COmanageAPIError`: API communication issues
- `COmanageUserError`: User-related errors
- `COmanageGroupsError`: Group management errors
- `COmanageAccountLinkingError`: General account linking errors

## Development

The plugin is designed to be extensible. Key classes:
- `COmanageAPI`: Handles API communication
- `COmanageUser`: Manages user information and status
- `COmanageAccountLinkingMicroService`: Main plugin logic

