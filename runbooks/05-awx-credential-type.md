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

You only need to provide two things:

| Variable | What it is | Example |
|---|---|---|
| `AWX` | Your AWX base URL. | `https://ansible.example.com` |
| `AUTH` | `admin:<password>` for the AWX admin (HTTP basic). | `admin:hunter2` |

Pick the snippet that matches the credential type you want. Each is
self-contained, requires no external tools, and prints back the new
credential type's `id`. Save that id; step 2 below needs it.

**Akeyless (Cert Auth)**:

```bash
AWX=https://ansible.example.com
AUTH=admin:hunter2

curl -sk -u "$AUTH" -H 'Content-Type: application/json' \
  -X POST "$AWX/api/v2/credential_types/" --data @- <<'JSON' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("CT_ID=" + str(d.get("id") or d))'
{
  "name": "Akeyless (Cert Auth)",
  "description": "Authenticate to Akeyless with a client certificate.",
  "kind": "cloud",
  "inputs": {
    "fields": [
      {"id": "akeyless_api_url", "label": "Akeyless API URL", "type": "string", "default": "https://api.akeyless.io"},
      {"id": "access_id",        "label": "Akeyless Access ID", "type": "string"},
      {"id": "cert_data",        "label": "Client Certificate (PEM)", "type": "string", "multiline": true},
      {"id": "key_data",         "label": "Client Private Key (PEM)", "type": "string", "multiline": true, "secret": true}
    ],
    "required": ["akeyless_api_url", "access_id", "cert_data", "key_data"]
  },
  "injectors": {
    "env": {
      "AKEYLESS_API_URL":     "{{ akeyless_api_url }}",
      "AKEYLESS_ACCESS_ID":   "{{ access_id }}",
      "AKEYLESS_ACCESS_TYPE": "cert",
      "AKEYLESS_CERT_FILE":   "{{ tower.filename.cert }}",
      "AKEYLESS_KEY_FILE":    "{{ tower.filename.key }}"
    },
    "file": {
      "template.cert": "{{ cert_data }}",
      "template.key":  "{{ key_data }}"
    }
  }
}
JSON
```

**Akeyless (API Key)**:

```bash
curl -sk -u "$AUTH" -H 'Content-Type: application/json' \
  -X POST "$AWX/api/v2/credential_types/" --data @- <<'JSON' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("CT_ID=" + str(d.get("id") or d))'
{
  "name": "Akeyless (API Key)",
  "description": "Authenticate to Akeyless with an access ID + access key.",
  "kind": "cloud",
  "inputs": {
    "fields": [
      {"id": "akeyless_api_url", "label": "Akeyless API URL", "type": "string", "default": "https://api.akeyless.io"},
      {"id": "access_id",        "label": "Akeyless Access ID", "type": "string"},
      {"id": "access_key",       "label": "Akeyless Access Key", "type": "string", "secret": true}
    ],
    "required": ["akeyless_api_url", "access_id", "access_key"]
  },
  "injectors": {
    "env": {
      "AKEYLESS_API_URL":     "{{ akeyless_api_url }}",
      "AKEYLESS_ACCESS_ID":   "{{ access_id }}",
      "AKEYLESS_ACCESS_TYPE": "api_key",
      "AKEYLESS_ACCESS_KEY":  "{{ access_key }}"
    }
  }
}
JSON
```

**Akeyless (Kubernetes Auth)**:

```bash
curl -sk -u "$AUTH" -H 'Content-Type: application/json' \
  -X POST "$AWX/api/v2/credential_types/" --data @- <<'JSON' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("CT_ID=" + str(d.get("id") or d))'
{
  "name": "Akeyless (Kubernetes Auth)",
  "description": "Authenticate to Akeyless with a Kubernetes ServiceAccount token.",
  "kind": "cloud",
  "inputs": {
    "fields": [
      {"id": "akeyless_api_url",         "label": "Akeyless API URL", "type": "string", "default": "https://api.akeyless.io"},
      {"id": "akeyless_gateway_url",     "label": "Akeyless Gateway URL", "type": "string"},
      {"id": "access_id",                "label": "Akeyless Access ID", "type": "string"},
      {"id": "k8s_auth_config_name",     "label": "K8s Auth Config Name", "type": "string"},
      {"id": "k8s_service_account_token","label": "ServiceAccount Token (optional)", "type": "string", "multiline": true, "secret": true},
      {"id": "validate_certs",           "label": "Validate Gateway TLS Certificate", "type": "boolean", "default": true}
    ],
    "required": ["akeyless_api_url", "akeyless_gateway_url", "access_id", "k8s_auth_config_name"]
  },
  "injectors": {
    "env": {
      "AKEYLESS_API_URL":              "{{ akeyless_api_url }}",
      "AKEYLESS_GATEWAY_URL":          "{{ akeyless_gateway_url }}",
      "AKEYLESS_ACCESS_ID":            "{{ access_id }}",
      "AKEYLESS_ACCESS_TYPE":          "k8s",
      "AKEYLESS_K8S_AUTH_CONFIG_NAME": "{{ k8s_auth_config_name }}",
      "AKEYLESS_K8S_SA_TOKEN":         "{{ k8s_service_account_token | default('') }}",
      "AKEYLESS_VALIDATE_CERTS":       "{{ validate_certs | default(true) | string | lower }}"
    }
  }
}
JSON
```

Each snippet prints `CT_ID=<n>` on success. If you see `CT_ID=` followed
by an error blob (a JSON object with a message instead of a number),
the most common cause is a name conflict — the credential type already
exists. List what's there with:

```bash
curl -sk -u "$AUTH" "$AWX/api/v2/credential_types/?search=akeyless" \
  | python3 -c 'import json,sys; [print(r["id"], r["name"]) for r in json.load(sys.stdin)["results"]]'
```

Reuse the existing `id` rather than recreating.

A reference Ansible-based provisioning playbook is at
`tests/integration/awx-setup.yml` (cert-auth flavor). It uses
`awx.awx.credential_type` instead of curl and works equally well if
you prefer Ansible-driven provisioning.

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
