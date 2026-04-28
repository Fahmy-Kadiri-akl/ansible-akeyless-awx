# AWX Custom Credential Type

This collection ships an AWX Custom Credential Type at
`extensions/awx/credential_types/akeyless_cert_auth.yml`. It defines the
fields a user fills in (URL, access ID, cert PEM, key PEM) and the
injectors that translate those fields into env vars and tempfile paths the
inventory plugin expects at job-run time.

You will:

1. Register the Custom Credential Type once, per AWX install.
2. Create a credential instance of that type for each cert and role pair
   you want AWX to use, typically one per environment (prod, staging, and
   so on).

## Step 1: register the Custom Credential Type

Navigate: **Administration -> Credential Types -> Add**.

| Field | Value |
|---|---|
| **Name** | `Akeyless (Cert Auth)` |
| **Description** | `Authenticate to Akeyless with a client certificate. Consumed by the akeyless.awx_integration.akeyless inventory plugin.` |
| **Input Configuration** | Paste the `inputs:` block from `extensions/awx/credential_types/akeyless_cert_auth.yml`. |
| **Injector Configuration** | Paste the `injectors:` block from the same file. |

Click **Save**.

### What the inputs declare

The credential type defines four user-facing fields:

| Field | Type | Default | Notes |
|---|---|---|---|
| **Akeyless API URL** | string | `https://api.akeyless.io` | The Akeyless SaaS API. Do not change this to a customer gateway URL; see [`04-akeyless-cert-auth.md`](04-akeyless-cert-auth.md) for the endpoint distinction. |
| **Akeyless Access ID** | string | none | For example `p-XXXXXXXXXXXXXX`. From the cert auth method in Akeyless. |
| **Client Certificate (PEM)** | multiline string | none | The full PEM, including the `-----BEGIN CERTIFICATE-----` and `-----END CERTIFICATE-----` lines. |
| **Client Private Key (PEM)** | multiline string, secret | none | Unencrypted private key matching the certificate. AWX masks this on subsequent views. |

All four are marked required.

### What the injectors do at job-run time

When AWX launches an inventory sync (or any job) that uses this credential,
the injectors fire inside the EE container and:

1. Write `cert_data` to a tempfile and `key_data` to a tempfile. AWX
   assigns the paths and exposes them as `{{ tower.filename.cert }}` and
   `{{ tower.filename.key }}`.
2. Set these env vars in the container:

| Env var | Value |
|---|---|
| `AKEYLESS_API_URL` | The URL field. |
| `AKEYLESS_ACCESS_ID` | The access ID field. |
| `AKEYLESS_ACCESS_TYPE` | Always `cert`. |
| `AKEYLESS_CERT_FILE` | Path to the cert tempfile. |
| `AKEYLESS_KEY_FILE` | Path to the key tempfile. |

The inventory plugin's options declare matching `env:` entries in their
DOCUMENTATION block, so `get_option('access_id')` and friends resolve
from these env vars without any explicit lookup code.

### Verify

The credential type appears under **Administration -> Credential Types**
with **Kind: Cloud**.

The credential type can also be created programmatically using
`awx.awx.credential_type` against an existing AWX. The reference playbook
at `tests/integration/awx-setup.yml` shows the full provisioning,
including this step.

## Step 2: create a credential instance

Navigate: **Resources -> Credentials -> Add**.

| Field | Value |
|---|---|
| **Name** | `akeyless-prod-cert` (or any descriptive label). |
| **Organization** | The org that will own AWX-side resources for this environment. |
| **Credential Type** | `Akeyless (Cert Auth)` (the one from step 1). |
| **Akeyless API URL** | `https://api.akeyless.io` |
| **Akeyless Access ID** | The access ID you used in [`04-akeyless-cert-auth.md`](04-akeyless-cert-auth.md). |
| **Client Certificate (PEM)** | Paste the full cert PEM. |
| **Client Private Key (PEM)** | Paste the full key PEM (unencrypted). |

Click **Save**. AWX masks the private key on the next view; that is
expected and correct.

### Verify

The credential appears under **Resources -> Credentials**, with
**Type = Akeyless (Cert Auth)**. Open it and confirm the URL and access
ID are what you expect; the key is masked.

To run multiple environments (prod, staging, dev) against different
Akeyless roles, create one credential instance per environment. They all
use the same Custom Credential Type.

## Next steps

- [Inventory source configuration](06-inventory-source.md). Wire the credential, the EE, and an inventory YAML together into an inventory source.
