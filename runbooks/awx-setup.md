# Runbook: Configure AWX/AAP to consume Akeyless secrets

> **Scope:** wire an existing AWX/AAP install to fetch secrets from your
> existing Akeyless deployment so playbooks consume them as ordinary
> host_vars / group_vars. Nothing in this guide deploys AWX or Akeyless;
> both are assumed to be running.
>
> **Outcome:** at the end you can run any playbook against an inventory
> whose host_vars are sourced live from Akeyless, with no Akeyless code
> in the playbook.
>
> **Estimated time:** ~20 minutes for the happy path; allow 30 if you
> need to fix cert-auth setup in Akeyless first.
>
> **Status:** validated against AWX 24.6.1 + the published reference EE
> at `ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:0.1.0`.

## Contents

1. [Prerequisites](#prerequisites)
2. [Step 1: verify Akeyless cert-auth works](#step-1-verify-akeyless-cert-auth-works)
3. [Step 2: pick or build the Execution Environment](#step-2-pick-or-build-the-execution-environment)
4. [Step 3: register the EE in AWX](#step-3-register-the-ee-in-awx)
5. [Step 4: create the Akeyless Custom Credential Type](#step-4-create-the-akeyless-custom-credential-type)
6. [Step 5: create a credential of that type](#step-5-create-a-credential-of-that-type)
7. [Step 6: create the inventory source YAML](#step-6-create-the-inventory-source-yaml)
8. [Step 7: create the inventory and inventory source](#step-7-create-the-inventory-and-inventory-source)
9. [Step 8: run a test playbook](#step-8-run-a-test-playbook)
10. [Day-2 operations](#day-2-operations)
11. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Confirm each item before starting. Most failures later in this runbook
trace back to a missed prerequisite here.

| Need | How to check |
|---|---|
| AWX or AAP admin access | Log in, see the Settings menu |
| Akeyless SaaS API reachable from the AWX cluster | From any AWX host: `curl -sI https://api.akeyless.io` returns HTTP headers (a 405 is normal — we are only testing TLS reachability to the SaaS API). |
| Cert-auth method exists in Akeyless | Akeyless console, **Auth Methods**, filter by type=Certificate; the access ID looks like `p-XXXXXXXXXXXXXX` |
| An access role grants read on the secret paths AWX will consume | Same role bound to the cert auth method; readable paths visible under **Items** |
| A client cert + private key issued by the CA the cert-auth method trusts | Two PEM files in hand (cert, unencrypted key) |
| `awx-ee` is the default EE | Settings -> Execution Environments shows `quay.io/ansible/awx-ee:latest` (this is what we replace at the inventory-source level) |

---

## Step 1: verify Akeyless cert-auth works

The most common failure mode in this whole runbook is "cert auth doesn't
actually work, but no error surfaces until the inventory plugin runs and
returns 401." Catch it now.

### Endpoint terminology (read this first)

Two distinct Akeyless endpoints exist, and they are not interchangeable
for cert auth:

- **Akeyless SaaS API:** `https://api.akeyless.io`. The public Akeyless
  service, hosted by Akeyless. This is where cert-auth handshakes must
  terminate.
- **Customer gateway (self-hosted):** the customer-deployed Akeyless
  Gateway, typically at `https://your-gateway.example.com:8000/api/v1`.
  Most customer gateway ingresses terminate TLS at the edge and do not
  forward TLS client certs through to the gateway pod, so cert-auth
  handshakes fail there. This is why the AWX credential type defaults
  the URL field to the SaaS endpoint.

The akeyless CLI selects an endpoint in this order of precedence
(verified against CLI 1.142.0; cert auth has no `--gateway-url` flag of
its own, so the URL is determined entirely by env var + profile):

1. `AKEYLESS_GATEWAY_URL` env var. If set, all calls route through it.
2. The active profile's `gateway_url` field, stored in
   `~/.akeyless/profiles/<profile>.toml`. Set or cleared via
   `akeyless configure --gateway-url <url>` (use `""` to clear).
3. Default: the Akeyless SaaS API.

For cert-auth verification both 1 and 2 must be empty so the CLI reaches
the SaaS API directly. Inspect the active profile with
`cat ~/.akeyless/profiles/default.toml` (or whatever profile name you use)
and confirm `gateway_url = ''`.

### Verify with the CLI

From any machine that has the cert and key. The `env -u` clears any
inherited `AKEYLESS_GATEWAY_URL` so the CLI falls back to the profile
or SaaS default:

```bash
env -u AKEYLESS_GATEWAY_URL akeyless auth \
  --access-id p-XXXXXXXXXXXXXX \
  --access-type cert \
  --cert-file-name /path/to/client.crt \
  --key-file-name /path/to/client.key
```

**Expected:** prints a token starting with `t-`.

**If it fails:**

- `failed to read certificate: open <path>: no such file or directory`:
  the path is wrong or the file is unreadable.
- `failed to get credentials: failed to parse private key`: the key
  PEM is malformed or encrypted.
- `Unauthorized via gateway: https://...`: the CLI routed through a
  customer gateway whose ingress is not forwarding TLS client certs
  (the gateway URL is echoed back in the error). Either `AKEYLESS_GATEWAY_URL`
  is still set, or the profile has a `gateway_url`. Re-run with
  `env -u AKEYLESS_GATEWAY_URL` and clear the profile setting via
  `akeyless configure --gateway-url ""`.
- `unauthorized: certificate not allowed` / TLS handshake error from
  the SaaS: the cert was not issued by the CA the auth method trusts,
  or has expired.
- `unauthorized: missing role`: the auth method is not bound to a role
  that grants read on the path AWX will consume.

Resolve before continuing. Do not try to debug this once it is buried
inside an AWX inventory sync log.

---

## Step 2: pick or build the Execution Environment

AWX 24.6.1 ships a default EE (`quay.io/ansible/awx-ee:latest`) that does
**not** contain the akeyless Python SDK, and AWX does **not** auto-install
project-level `requirements.txt` for inventory updates. The SDK must be
baked into the EE.

You have two options.

### Option A (recommended): use the published reference image

```
ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:0.1.0
```

Built on `quay.io/ansible/awx-ee:latest`, adds
`akeyless.secrets_management`, `akeyless.awx_integration`, and the
`akeyless` Python SDK. Public; pulls require no auth. Rebuilt weekly by
the `ee-build.yml` workflow.

**Verify the image is reachable:**

```bash
docker pull ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:0.1.0
```

### Option B: build your own

For environments with private registries, custom bases, or internal
supply-chain controls, the `ee/` directory is a working ansible-builder v3
context.

```bash
cd ee
ansible-builder build \
  -t your-registry.example/akeyless-awx-ee:0.1.0 \
  -f execution-environment.yml \
  --container-runtime docker
docker push your-registry.example/akeyless-awx-ee:0.1.0
```

The build pulls the latest `quay.io/ansible/awx-ee` base, installs pinned
collection and Python deps, and bakes this collection in.

---

## Step 3: register the EE in AWX

Navigate: **Administration -> Execution Environments -> Add**.

- **Name:** `akeyless-awx-ee` (or any label you prefer)
- **Image:** the GHCR URL from Option A, or what you pushed in Option B
- **Pull policy:** `always` for prod (so weekly rebuilds are picked up
  automatically), `missing` for first-time tests
- **Credential:** none required for the public GHCR image; use a
  registry credential if you went with Option B and a private registry

Save.

**Verify:** the EE appears in the list and is selectable from the
inventory-source EE dropdown later.

---

## Step 4: create the Akeyless Custom Credential Type

Navigate: **Administration -> Credential Types -> Add**.

The source YAML is at
`extensions/awx/credential_types/akeyless_cert_auth.yml`. Copy the
`inputs:` block into the **Input Configuration** field and the
`injectors:` block into the **Injector Configuration** field.

The four user-facing fields the type defines:

- **Akeyless API URL** (default `https://api.akeyless.io`). This is the
  Akeyless SaaS API. Do not change it to a customer gateway URL unless
  you have verified that your gateway ingress passes TLS client cert
  payloads through to the gateway pod. (Most do not. See [Step 1](#step-1-verify-akeyless-cert-auth-works) for the
  endpoint distinction.)
- **Akeyless Access ID** (e.g. `p-XXXXXXXXXXXXXX`).
- **Client Certificate (PEM)**, multiline.
- **Client Private Key (PEM)**, multiline, marked secret.

The injectors expose these to inventory updates at job-run time:

- `AKEYLESS_API_URL`, `AKEYLESS_ACCESS_ID`, `AKEYLESS_ACCESS_TYPE=cert`
- `AKEYLESS_CERT_FILE`, `AKEYLESS_KEY_FILE` (paths to tempfiles AWX writes
  from the `cert_data` / `key_data` PEM payloads)

Save.

**Verify:** the credential type appears under Credential Types with
**Kind: Cloud**.

---

## Step 5: create a credential of that type

Navigate: **Resources -> Credentials -> Add**.

- **Name:** `akeyless-prod-cert` (or whatever)
- **Credential Type:** the one from Step 4
- **Akeyless API URL:** `https://api.akeyless.io`
- **Akeyless Access ID:** the value you used in Step 1
- **Client Certificate (PEM):** paste the cert PEM
- **Client Private Key (PEM):** paste the key PEM

Save. AWX masks the private key on subsequent views; that is expected.

---

## Step 6: create the inventory source YAML

The inventory plugin reads its config from a YAML file inside an AWX
Project. The project just needs to be a Git repo with the YAML at a known
path. Use any SCM (GitHub, GitLab, internal, etc.).

Two modes are supported. **Path discovery is recommended** because adding
a new secret in Akeyless then requires no AWX change at all.

### Path discovery (recommended)

```yaml
# inventory.akeyless.yml
plugin: akeyless.awx_integration.akeyless
secret_path_prefix: /apps/prod
hosts:
  - app01.example.com
  - app02.example.com
default_group: prod_apps
```

A secret at `/apps/prod/db/password` becomes the variable `db_password`
on every host. Adjust naming via `var_name_template` if needed.

### Explicit mapping

```yaml
plugin: akeyless.awx_integration.akeyless
secrets:
  - name: /apps/prod/db_password
    var: db_password
  - name: /apps/prod/api_token
    var: api_token
```

The two modes are combinable: `secret_path_prefix` for bulk discovery,
`secrets` for fixed-name overrides.

> **Do not** put `access_id`, `cert_file`, `key_file`, or `akeyless_api_url`
> in this YAML. They are injected by the AWX credential at job-run time. If
> you put them here they will be ignored at best and conflict at worst.

Commit and push the YAML to the project's Git repo. In AWX, **Resources ->
Projects -> Add** if you do not have a project yet; point at the SCM URL
and sync.

**Verify:** the project shows status "Successful" after the sync.

---

## Step 7: create the inventory and inventory source

Navigate: **Resources -> Inventories -> Add -> Inventory** (the regular
kind, not "Smart Inventory").

- **Name:** `akeyless-prod`
- **Organization:** as appropriate

Save, then in the inventory's **Sources** tab click **Add**.

- **Name:** `akeyless`
- **Source:** "Sourced from a Project"
- **Project:** the project from Step 6
- **Inventory file:** the YAML path, e.g. `inventory.akeyless.yml`
- **Credential:** the one from Step 5
- **Execution Environment:** the EE from Step 3 (set this on the source
  itself; AWX picks the source's EE for inventory updates, not the
  system default)
- **Update on launch:** yes (so jobs always see fresh secret values)

Save and click **Sync**.

**Expected:** "Successful" status. The inventory's **Hosts** tab now
lists the hosts from your YAML, each with the discovered secrets attached
as host_vars.

**Verify:** click any host and inspect the **Variables** panel; you
should see the variables derived from your `secret_path_prefix`. Secret
values are masked in the UI by default; that is expected.

---

## Step 8: run a test playbook

**Resources -> Templates -> Add -> Job Template**. Reference the
inventory and EE. Use any existing playbook; secrets are consumed as
ordinary host_vars.

```yaml
- hosts: prod_apps
  tasks:
    - name: Use the API token
      ansible.builtin.uri:
        url: https://api.example.com/v1/data
        headers:
          Authorization: 'Bearer {{ api_token }}'
```

No Akeyless lookups, no logins, no cert handling. Launch the template.

**Expected:** the job completes successfully against all hosts in the
group. If it does, the integration is wired correctly end to end.

---

## Day-2 operations

- **Rotation:** rotate a secret in Akeyless. The next inventory sync
  (which fires on launch when "Update on launch" is enabled) picks up the
  new value, and the next job run uses it.
- **Adding a secret:** create the secret under `secret_path_prefix` in
  Akeyless. It appears as a new host_var on the next sync. Existing
  playbooks remain unchanged; new playbooks reference the new variable
  by the path-derived name.
- **Removing a secret:** delete it in Akeyless or remove it from the
  access role. It disappears from the inventory on the next sync.
- **Revoking access:** revoke the cert at the auth method or remove the
  role association. Subsequent syncs fail with a clear 401 before any
  job runs.
- **Image refresh:** the published GHCR image is rebuilt every Monday by
  `ee-build.yml`. With pull policy `always`, AWX picks up the new image
  on the next inventory sync. To pin a known-good image, switch to a
  tagged weekly build like `:weekly-2026-04-21`.

---

## Troubleshooting

### Inventory sync fails with `ModuleNotFoundError: No module named 'akeyless'`

The EE does not contain the Python SDK. Either you registered the wrong
EE in Step 3, or the inventory source is using the system default EE
instead of the akeyless one. Re-check **Execution Environment** on the
inventory *source*, not the inventory.

### Inventory sync fails with `401 Unauthorized` from Akeyless

Cert auth is failing. Re-run Step 1 with the same cert + key from a
shell. If that succeeds but the AWX sync still fails:

- Confirm **Akeyless API URL** in the credential is `https://api.akeyless.io`,
  not a customer gateway URL.
- Confirm the credential's PEM payloads are correct (no trailing
  whitespace inside the PEM headers/footers, key not encrypted).
- Confirm the cert is not expired.

### Inventory sync succeeds but no host_vars show up

Either the access role does not grant read on `secret_path_prefix`, or
no secrets exist there.

In the Akeyless console, open **Items**, navigate to the
`secret_path_prefix` value (or filter by it), and confirm two things:

1. Items exist under that path.
2. The access role bound to the cert auth method has read on them.

If both are true and the sync still returns no host_vars, capture the
inventory-update job log from AWX (Jobs -> the failed inventory sync
-> Output) and look for the plugin's per-item log lines, which name
exactly which secrets it tried to fetch and what response it got.

### Job picks up an old secret value after rotation in Akeyless

"Update on launch" is not enabled on the inventory source, so AWX is
using a cached sync. Enable it, or sync the source manually before
launching the job.

### Cert auth fails because the credential points at a customer gateway

The credential has a customer gateway URL (typically
`https://your-gw:8000/api/v1`) in **Akeyless API URL**. Customer gateway
ingresses do not pass TLS client cert payloads through by default.
Switch the URL to the SaaS API at `https://api.akeyless.io`. See
[Step 1](#step-1-verify-akeyless-cert-auth-works) for the endpoint
distinction.

### Project sync fails with "inventory file not found"

The path you typed in the inventory source does not match the file in
the Git repo. Inventory file paths are relative to the project root.

### `awx-ee` is being used despite registering the akeyless EE

Two places set the EE: a system-wide default in Settings, and per-source
on the inventory source itself. Inventory updates use the source's
setting. Set it on the source.
