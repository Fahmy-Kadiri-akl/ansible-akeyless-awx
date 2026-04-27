# Configuring AWX/AAP to consume Akeyless secrets

This walks you through wiring an existing AWX/AAP install to fetch secrets
from your existing Akeyless deployment so that playbooks consume them as
ordinary host_vars / group_vars. Nothing in this guide deploys AWX or
Akeyless; both are assumed to be running.

## Prerequisites

- AWX or AAP, admin access via the API.
- Akeyless gateway reachable from the AWX cluster, or the SaaS endpoint at
  https://api.akeyless.io.
- A cert auth method in Akeyless, bound to a CA you can issue client certs
  from, associated with an access role that grants read on the secret paths
  AWX will consume.
- A throwaway client cert + private key issued from the trusted CA, for
  testing. PepsiCo-prod or similar will use their PKI.

## 1. Pick an Execution Environment

AWX 24.6.1 ships a default EE (`quay.io/ansible/awx-ee:latest`) that does
**not** contain the akeyless Python SDK, and AWX does **not** auto-install
project-level `requirements.txt` for inventory updates. The SDK must be
baked into the EE.

You have two options.

**Option A (recommended) — use the published reference image.** This repo
publishes a verified-working EE on GHCR:

```
ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:0.1.0
```

It is built on `quay.io/ansible/awx-ee:latest` and adds
`akeyless.secrets_management`, `akeyless.awx_integration`, and the
`akeyless` Python SDK. The package is public; pulls do not require
authentication.

**Option B — build your own.** For environments with private registries,
custom bases, or internal supply-chain controls, this repo's `ee/`
directory is a working ansible-builder v3 context:

```bash
cd ee
ansible-builder build -t your-registry.example/akeyless-awx-ee:0.1.0 \
  -f execution-environment.yml --container-runtime docker
docker push your-registry.example/akeyless-awx-ee:0.1.0
```

## 2. Register the EE in AWX

Settings -> Execution Environments -> Add. Image: either
`ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:0.1.0` (Option A) or whatever
you pushed in Option B. Pull policy: `always` for prod, `missing` for
first-time tests.

## 3. Create the Akeyless Custom Credential Type

Administration -> Credential Types -> Add. Use the YAML in
`extensions/awx/credential_types/akeyless_cert_auth.yml`. The fields are:

- Akeyless API URL (defaults to https://api.akeyless.io)
- Access ID
- Client Certificate (PEM, multiline)
- Client Private Key (PEM, multiline, secret)

Injectors write cert/key to tempfile paths and expose them via env vars the
inventory plugin reads:

- `AKEYLESS_API_URL`, `AKEYLESS_ACCESS_ID`, `AKEYLESS_ACCESS_TYPE=cert`
- `AKEYLESS_CERT_FILE`, `AKEYLESS_KEY_FILE` (paths to tempfiles)

> Cert auth must hit `https://api.akeyless.io`. Customer-hosted gateway
> ingresses typically do not pass cert-auth payloads through.

## 4. Create a credential of that type

Resources -> Credentials -> Add. Type: the credential type from step 3. Fill
in the four fields with values for your Akeyless gateway and the client
cert/key issued from the trusted CA.

## 5. Create or reuse a Project that holds the inventory source YAML

Projects -> Add. Use any SCM Git source. The project just needs to contain a
single YAML file like:

```yaml
# inventory.akeyless.yml — path-discovery mode (recommended)
plugin: akeyless.awx_integration.akeyless
secret_path_prefix: /apps/prod
hosts:
  - app01.example.com
  - app02.example.com
default_group: prod_apps
```

Notes:

- **Do not** put `access_id`, `cert_file`, `key_file`, or
  `akeyless_api_url` in this file. They are injected by the AWX credential
  at job-run time.
- Variables are derived from the path under `secret_path_prefix`. With
  `secret_path_prefix: /apps/prod` and a secret at
  `/apps/prod/db/password`, the resulting variable is `db_password`.
- For a fixed naming contract, use the explicit form instead:

  ```yaml
  plugin: akeyless.awx_integration.akeyless
  secrets:
    - name: /apps/prod/db_password
      var: db_password
    - name: /apps/prod/api_token
      var: api_token
  ```

## 6. Create an inventory + inventory source

Inventories -> Add. Then Sources -> Add:

- Source: 'Sourced from a Project'
- Project: the project from step 5
- Inventory file: the YAML file from step 5
- Credential: the credential from step 4
- Execution Environment: the EE from step 2 (set this on the source itself —
  AWX picks the source's EE for inventory updates, not the system default)
- Update on launch: yes

Save and 'Sync'. The inventory should populate with the hosts from your YAML
plus every secret under the prefix attached as host_vars.

## 7. Create or update job templates

Templates -> Add. Reference the inventory and the EE. The playbook is
**any** existing playbook — it consumes the discovered variables as ordinary
host_vars.

```yaml
- hosts: prod_apps
  tasks:
    - name: Use the API token
      ansible.builtin.uri:
        url: https://api.example.com/v1/data
        headers:
          Authorization: 'Bearer {{ api_token }}'
```

No Akeyless lookups, no logins, no cert handling.

## 8. Day-2 operations

- **Rotation:** rotate a secret in Akeyless. Next inventory sync (which fires
  on launch when 'Update on launch' is enabled) picks up the new value.
- **Adding a secret:** create the secret under `secret_path_prefix` in
  Akeyless. It appears as a new host_var on the next sync. Existing
  playbooks remain unchanged; new playbooks reference the new variable by
  the path-derived name.
- **Removing a secret:** delete it in Akeyless or the access role. It
  disappears from the inventory on the next sync.
- **Revoking access:** revoke the cert at the auth method or remove the
  role association. Subsequent syncs fail with a clear 401, before any job
  runs.
