# AWX Custom Credential Type

This collection ships three Custom Credential Types under
`extensions/awx/credential_types/`. Each one declares the fields a user
fills in plus the injectors that translate those fields into env vars
the inventory plugin expects at job-run time.

| File | Credential type | Use when |
|---|---|---|
| `akeyless_cert_auth.yml` | `Akeyless (Cert Auth)` | TLS client cert + key, recommended for most controllers. |
| `akeyless_api_key.yml` | `Akeyless (API Key)` | Pre-shared `access_id` + `access_key`. |
| `akeyless_k8s_auth.yml` | `Akeyless (Kubernetes Auth)` | AWX runs in Kubernetes and a customer Akeyless gateway is reachable. |

You will:

1. Register one or more Custom Credential Types, once per AWX install.
2. Create a credential instance of the type you registered, one per
   environment (prod, staging, and so on).

## Step 1: register the Custom Credential Type

Navigate: **Administration -> Credential Types -> Add**.

| Field | Value |
|---|---|
| **Name** | The `name:` field from the YAML you picked. |
| **Description** | The `description:` field from the YAML. |
| **Input Configuration** | Paste the `inputs:` block from the same YAML. |
| **Injector Configuration** | Paste the `injectors:` block from the same YAML. |

Click **Save**.

> **Important:** the canonical YAMLs write injector values as plain
> Jinja (`{{ access_key }}`, `{{ tower.filename.cert }}`). Do **not**
> wrap them in `{% raw %}` markers when pasting into the AWX UI; AWX
> would store the literal text and the inventory plugin would try to
> read a path or env value of `{{ ... }}`. The reference provisioning
> playbook at `tests/integration/awx-setup.yml` uses an inline copy
> with `{% raw %}` blocks because Ansible itself templates the YAML
> before posting it to AWX. The two files are intentionally different.

### Or, via API

```bash
curl -sk -u "<admin>:<pass>" \
  -H 'Content-Type: application/json' \
  -X POST https://<awx-host>/api/v2/credential_types/ \
  -d '{
    "name": "<from YAML>",
    "description": "<from YAML>",
    "kind": "cloud",
    "inputs": { /* paste the inputs block as JSON */ },
    "injectors": { /* paste the injectors block as JSON */ }
  }'
```

A reference Ansible-based provisioning playbook is at
`tests/integration/awx-setup.yml` (cert-auth flavor). The same pattern
applies to the other two types.

### What the inputs declare (per type)

#### `Akeyless (Cert Auth)`

| Field | Type | Default | Notes |
|---|---|---|---|
| **Akeyless API URL** | string | `https://api.akeyless.io` | The Akeyless SaaS API. Do not change this to a customer gateway URL; see [`04-akeyless-cert-auth.md`](04-akeyless-cert-auth.md) for the endpoint distinction. |
| **Akeyless Access ID** | string | required | For example `p-XXXXXXXXXXXXXX`. From the cert auth method in Akeyless. |
| **Client Certificate (PEM)** | multiline string | required | The full PEM, including the `-----BEGIN CERTIFICATE-----` and `-----END CERTIFICATE-----` lines. |
| **Client Private Key (PEM)** | multiline string, secret | required | Unencrypted private key matching the certificate. AWX masks this on subsequent views. |

#### `Akeyless (API Key)`

| Field | Type | Default | Notes |
|---|---|---|---|
| **Akeyless API URL** | string | `https://api.akeyless.io` | The Akeyless SaaS API. |
| **Akeyless Access ID** | string | required | The access ID of the API-Key auth method. |
| **Akeyless Access Key** | string, secret | required | The access key paired with the access ID. AWX masks this on subsequent views. |

#### `Akeyless (Kubernetes Auth)`

| Field | Type | Default | Notes |
|---|---|---|---|
| **Akeyless API URL** | string | `https://api.akeyless.io` | The Akeyless SaaS API. |
| **Akeyless Gateway URL** | string | required | Customer gateway, e.g. `https://your-gateway.example.com:8000/api/v1`. K8s auth is gateway-mediated; the gateway calls Kubernetes TokenReview. |
| **Akeyless Access ID** | string | required | The access ID of the K8s auth method. |
| **K8s Auth Config Name** | string | required | The K8s auth config within the auth method (one auth method may map to multiple clusters). |
| **ServiceAccount Token (optional)** | multiline string, secret | empty | Paste a JWT to override the auto-mounted SA token. Leave blank if AWX runs in-cluster; the inventory plugin reads `/var/run/secrets/kubernetes.io/serviceaccount/token` from the EE pod. |

### What the injectors do at job-run time

When AWX launches an inventory sync that uses one of these credentials,
the injectors set env vars inside the EE container. The inventory
plugin's options declare matching `env:` entries so `get_option(...)`
resolves from those env vars without any explicit lookup code.

| Env var | Set by | Value |
|---|---|---|
| `AKEYLESS_API_URL` | all three | The URL field. |
| `AKEYLESS_ACCESS_ID` | all three | The access ID field. |
| `AKEYLESS_ACCESS_TYPE` | all three | `cert`, `api_key`, or `k8s` literal. |
| `AKEYLESS_CERT_FILE`, `AKEYLESS_KEY_FILE` | cert | Paths to tempfiles AWX writes from `cert_data` / `key_data`. |
| `AKEYLESS_ACCESS_KEY` | api-key | The access key. |
| `AKEYLESS_GATEWAY_URL` | k8s | The customer gateway URL. |
| `AKEYLESS_K8S_AUTH_CONFIG_NAME` | k8s | The K8s auth config name. |
| `AKEYLESS_K8S_SA_TOKEN` | k8s | Optional explicit JWT. Empty if relying on the in-pod path. |

### Verify

The credential type appears under **Administration -> Credential Types**
with **Kind: Cloud**.

## Step 2: create a credential instance

Navigate: **Resources -> Credentials -> Add**.

| Field | Value |
|---|---|
| **Name** | A descriptive label, e.g. `akeyless-prod-cert`, `akeyless-prod-apikey`, `akeyless-prod-k8s`. |
| **Organization** | The org that will own AWX-side resources for this environment. |
| **Credential Type** | The one you registered in step 1. |
| **(remaining fields)** | Fill in based on which auth method this credential carries; see the per-type tables above for what each field means. |

Click **Save**. AWX masks any field marked secret on the next view; that
is expected.

### Verify

The credential appears under **Resources -> Credentials** with
**Type = (the type you picked)**. Open it and confirm the non-secret
fields are what you expect.

To run multiple environments (prod, staging, dev) against different
Akeyless roles, create one credential instance per environment. They
can all use the same Custom Credential Type, or you can mix types per
environment.

## Next steps

- [Inventory source configuration](06-inventory-source.md). Wire the credential, the EE, and an inventory YAML together into an inventory source.
