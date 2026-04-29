# Inventory Source Configuration

The inventory plugin reads its configuration from a YAML file inside an
AWX Project. This step covers:

1. Writing the inventory YAML.
2. Committing it to a Git repo and registering that repo as an AWX
   Project.
3. Creating an Inventory and binding the YAML, the credential
   (from [step 05](05-awx-credential-type.md)), and the EE
   (from [step 03](03-execution-environment.md)) together as an Inventory
   Source.

## Step 1: write the inventory YAML

Filename rule: the plugin's `verify_file()` only accepts files whose name
ends with `akeyless.yml` or `akeyless.yaml`. Any other filename is
silently skipped by AWX.

Two discovery modes are supported. They can be combined.

### Path discovery (recommended)

Auto-discover every static secret under a path prefix. Adding a new secret
in Akeyless then requires no AWX or playbook change.

```yaml
# inventory.akeyless.yml
plugin: akeyless.awx_integration.akeyless
secret_path_prefix: /apps/prod
hosts:
  - app01.example.com
  - app02.example.com
default_group: prod_apps
```

A secret at `/apps/prod/db/password` becomes the variable `db_password` on
every host listed under `hosts` (and on `default_group` if set).

A ready-to-use copy of this file is committed at
`examples/inventory.akeyless.yml` in this repo, so you can point an AWX
project at this repo and use `examples/inventory.akeyless.yml` as the
**Inventory file** path without writing your own.

### Explicit name-to-var mapping

Use this when you need a fixed naming contract independent of the Akeyless
path:

```yaml
plugin: akeyless.awx_integration.akeyless
secrets:
  - name: /apps/prod/db_password
    var: db_password
  - name: /apps/prod/api_token
    var: api_token
hosts:
  - app01.example.com
```

### Combined

`secret_path_prefix` for bulk discovery, `secrets:` for fixed-name
overrides:

```yaml
plugin: akeyless.awx_integration.akeyless
secret_path_prefix: /apps/prod
secrets:
  - name: /apps/prod/legacy/db
    var: legacy_db_password
hosts:
  - app01.example.com
default_group: prod_apps
```

### Rotated and dynamic secrets

Beyond static secrets, the plugin also dispatches lookups to the
appropriate Akeyless API for rotated and dynamic secrets. Set the
`type:` field on a `secrets:` entry, or include the type in
`secret_types:` to have path-discovery pick them up.

Behavior per type:

| Type | API call | Returned shape | Per-sync behavior |
|---|---|---|---|
| `static-secret` | `get_secret_value` (batched) | string | Same value until the secret is updated. |
| `rotated-secret` | `get_rotated_secret_value` (per secret) | dict with the credential fields the rotator manages (e.g. `{username, password}` for a postgresql password rotator) | Each sync sees the current rotated value. With **Update on launch** enabled, every job sees the value Akeyless most recently rotated to. |
| `dynamic-secret` | `get_dynamic_secret_value` (per secret) | dict (multi-field ephemeral credential, e.g. `{id, password, ttl_in_minutes, user}` for a postgresql producer) | Each sync mints a fresh credential with a TTL. With **Update on launch** enabled, every job gets a brand-new credential. |

Both rotated and dynamic come back as dicts; access sub-fields with
normal Jinja:

```yaml
ansible_user: "{{ db_admin.username }}"
ansible_password: "{{ db_admin.password }}"
```

> **Important: rotated and dynamic reads need a customer gateway.**
> The plugin sends data calls (`list-items`, `get-rotated-secret-value`,
> `get-dynamic-secret-value`) to whichever URL is on the credential's
> **Akeyless Gateway URL** field. The auth handshake itself still
> goes to the SaaS for cert and api-key auth. Set the gateway URL on
> the AWX credential — see [`step 05`](05-awx-credential-type.md#or-via-api).

> **Per-sync TTL caveat.** Dynamic-secret credentials carry a TTL set
> by the Akeyless target. With `update_on_launch: true` the credential
> is minted seconds before the play starts, so a 5-minute TTL is
> usually fine. Long-running plays that exceed the TTL will have their
> credentials revoked mid-play and silently fail. If you have plays
> that run longer than the shortest dynamic-secret TTL, raise the TTL
> on the Akeyless side.

Per-type example files committed in this repo:

| File | Scope |
|---|---|
| [`examples/inventory.akeyless.yml`](../examples/inventory.akeyless.yml) | Static only (the simplest case). |
| [`examples/rotated.akeyless.yml`](../examples/rotated.akeyless.yml) | Rotated only. |
| [`examples/dynamic.akeyless.yml`](../examples/dynamic.akeyless.yml) | Dynamic only. |
| [`examples/multi-secret.akeyless.yml`](../examples/multi-secret.akeyless.yml) | All three under one `secret_path_prefix`. |
| [`examples/ssh-cert.akeyless.yml`](../examples/ssh-cert.akeyless.yml) | SSH-cert signing (covered in [runbook 10](10-ssh-cert.md)). |

### SSH-cert signing (just-in-time)

For just-in-time signed SSH certificates: configure the plugin with
the issuer name, the username to sign for, and where the SSH keypair
lives. On each sync the plugin calls `get-ssh-certificate` and
attaches three host_vars per host:

| host_var | Source |
|---|---|
| `akeyless_ssh_signed_cert` | The signed certificate string returned by Akeyless. |
| `akeyless_ssh_private_key` | Read from the static secret named in `ssh_cert_private_key_secret`. |
| `akeyless_ssh_cert_username` | The `ssh_cert_username` option, mirrored back for the role to consume. |

Example (also committed at `examples/ssh-cert.akeyless.yml`):

```yaml
plugin: akeyless.awx_integration.akeyless
hosts:
  - app01.example.com
default_group: ssh_cert_demo

ssh_cert_issuer: /5-SSH-CERT-ISSUER/SSH/your-issuer
ssh_cert_username: ubuntu
ssh_cert_private_key_secret: /apps/prod/ssh_private_key
ssh_cert_public_key: ssh-rsa AAAA...your-public-key... user@host
```

In the playbook, `import_role: name=akeyless.awx_integration.ssh_cert`
at the top of the play. The role materializes the cert and key into
tempfiles inside the EE pod and wires `ansible_user`,
`ansible_ssh_private_key_file`, and `ansible_ssh_extra_args` to use
them. See [`runbooks/10-ssh-cert.md`](10-ssh-cert.md) for the full
SSH-cert flow including the prerequisites on the Akeyless side.

### All supported options

| Option | Purpose |
|---|---|
| `plugin` | Always `akeyless.awx_integration.akeyless`. Required. |
| `secret_path_prefix` | Akeyless path prefix to auto-discover under. |
| `secrets` | Explicit `[{name, var, type, args}, ...]` mapping. `type` defaults to `static-secret`; `args` is only honored for `dynamic-secret`. |
| `var_name_template` | How to derive variable names from discovered paths. Default `{relpath}`. Other placeholders: `{basename}` (last segment) and `{fullname}` (full path). Non-identifier characters are replaced with `_`. |
| `secret_types` | Akeyless item types to discover. Default `['static-secret']`. Other valid values: `rotated-secret`, `dynamic-secret`. |
| `hosts` | List of host names to attach variables to. |
| `groups` | Mapping of `group_name: [host, ...]`. Variables are attached at the group level. |
| `default_group` | Umbrella group containing every host or group created. Default `akeyless_managed`. |
| `ssh_cert_issuer` | Akeyless SSH cert issuer name. When set, the plugin signs `ssh_cert_public_key` on each sync. |
| `ssh_cert_username` | Cert subject. Must appear in the issuer's `allowed_users` list (or match a wildcard). |
| `ssh_cert_principals` | Optional list of additional valid principals. |
| `ssh_cert_public_key` | Inline SSH public key to sign. Mutually exclusive with `ssh_cert_public_key_secret`. |
| `ssh_cert_public_key_secret` | Akeyless static-secret path holding the SSH public key. Takes precedence over `ssh_cert_public_key`. |
| `ssh_cert_private_key_secret` | Akeyless static-secret path holding the matching SSH private key. Required when `ssh_cert_issuer` is set. |

Do not put `access_id`, `cert_file`, `key_file`, or `akeyless_api_url` in
this YAML. They are injected by the AWX credential at job-run time. If you
put them here you encourage users to commit cert paths into Git.

## Step 2: commit and register the project

### Commit the YAML

Commit `inventory.akeyless.yml` to a Git repo at any path. Push.

```bash
git add inventory.akeyless.yml
git commit -m "Add Akeyless inventory source for prod apps"
git push
```

### Create the AWX Project

Navigate: **Resources -> Projects -> Add**.

| Field | Value |
|---|---|
| **Name** | `Akeyless inventory sources` (or any label). |
| **Organization** | Same org as the credential. |
| **Source Control Type** | `Git`. |
| **Source Control URL** | The HTTPS URL of the repo. |
| **Source Control Branch/Tag/Commit** | `main` (or your branch). |
| **Update Revision on Launch** | enabled, so AWX always uses the latest YAML. |
| **Credential** | A Git credential, if the repo is private. |

Click **Save**. AWX runs an initial project sync.

### Verify

In the UI: **Resources -> Projects**, the project shows
**Last Job Status: Successful** within about 30 seconds. Hover over
the status to see the timestamp.

Or, via API:

```bash
PROJECT_ID=$(curl -sk -u "$AUTH" "$AWX/api/v2/projects/?name=Akeyless%20inventory%20sources" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["results"][0]["id"])')

# Poll status until terminal
while true; do
  s=$(curl -sk -u "$AUTH" "$AWX/api/v2/projects/$PROJECT_ID/" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  echo "  status=$s"
  case "$s" in successful|failed|error) break;; esac
  sleep 5
done
echo "PROJECT_ID=$PROJECT_ID"
```

Expected: `status=successful`. Save the `PROJECT_ID`; the inventory
source in step 3 needs it.

If it fails, fetch the SCM output the same way:

```bash
LAST_UPDATE=$(curl -sk -u "$AUTH" "$AWX/api/v2/projects/$PROJECT_ID/" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["summary_fields"]["last_job"]["id"])')
curl -sk -u "$AUTH" "$AWX/api/v2/project_updates/$LAST_UPDATE/stdout/?format=txt" | tail -30
```

Most failures are SSH/HTTPS auth issues against the Git host, not
Akeyless-related.

## Step 3: create the inventory and inventory source

### Create the Inventory

Navigate: **Resources -> Inventories -> Add -> Inventory** (the regular
kind, not "Smart Inventory").

| Field | Value |
|---|---|
| **Name** | `akeyless-prod`. |
| **Organization** | Same org as before. |

Click **Save**.

### Create the Inventory Source

Open the inventory you just created. Click the **Sources** tab, then
**Add**.

| Field | Value |
|---|---|
| **Name** | `akeyless`. |
| **Source** | `Sourced from a Project`. |
| **Project** | The project from step 2. |
| **Inventory file** | The YAML path inside the repo. With this repo as your project: `examples/inventory.akeyless.yml`. With your own repo: the path you committed (e.g. `inventory.akeyless.yml`). |
| **Credential** | The credential from [step 05](05-awx-credential-type.md). |
| **Execution Environment** | The EE from [step 03](03-execution-environment.md). Set this on the source, not on the inventory or as the system default. AWX uses the source's EE for inventory updates. |
| **Update on launch** | enabled, so every job sees fresh secret values. |

Click **Save**.

> **The Inventory file dropdown will not list `inventory.akeyless.yml`
> automatically.** AWX populates the dropdown by inspecting the project
> tree for files it recognizes as static inventories. A plugin-style
> YAML (no static `hosts` section, just `plugin: ...`) is not
> auto-detected. Type the path manually.

### Or, via API

Set shell variables once, then run each call:

```bash
AWX=https://<awx-host>
AUTH="admin:<password>"
ORG_ID=1                # from /api/v2/organizations/?name=Default
PROJECT_ID=...          # from step 2 above
CREDENTIAL_ID=...       # from step 05
EE_ID=...               # from step 03

# Create the inventory
INV_ID=$(curl -sk -u "$AUTH" -H 'Content-Type: application/json' \
  -X POST "$AWX/api/v2/inventories/" \
  -d "{\"name\":\"akeyless-prod\",\"organization\":$ORG_ID}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "INV_ID=$INV_ID"

# Create the inventory source bound to project, credential, and EE
SRC_ID=$(curl -sk -u "$AUTH" -H 'Content-Type: application/json' \
  -X POST "$AWX/api/v2/inventory_sources/" \
  -d "{
    \"name\":\"akeyless\",
    \"inventory\":$INV_ID,
    \"source\":\"scm\",
    \"source_project\":$PROJECT_ID,
    \"source_path\":\"examples/inventory.akeyless.yml\",
    \"credential\":$CREDENTIAL_ID,
    \"execution_environment\":$EE_ID,
    \"update_on_launch\":true,
    \"overwrite\":true,
    \"overwrite_vars\":true
  }" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "SRC_ID=$SRC_ID"
```

Some AWX versions ignore the `credential` field on inventory-source
create. If `/api/v2/inventory_sources/$SRC_ID/credentials/` returns an
empty list afterwards, attach the credential explicitly:

```bash
curl -sk -u "$AUTH" -H 'Content-Type: application/json' \
  -X POST "$AWX/api/v2/inventory_sources/$SRC_ID/credentials/" \
  -d "{\"id\":$CREDENTIAL_ID}"
```

> **Why "Update on launch"?** Without it, AWX uses the inventory it cached
> the last time you manually clicked **Sync**. A secret rotated in
> Akeyless after that sync will not reach the next job until you sync
> again. The cost of enabling it is one extra sync per job launch,
> typically under 5 seconds.

## Next steps

- [First sync and test job](07-first-sync-and-job.md). Run the inventory sync, inspect the discovered host_vars, and run a job template that consumes one of them.
