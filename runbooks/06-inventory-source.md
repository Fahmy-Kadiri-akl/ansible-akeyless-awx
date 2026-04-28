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

### All supported options

| Option | Purpose |
|---|---|
| `plugin` | Always `akeyless.awx_integration.akeyless`. Required. |
| `secret_path_prefix` | Akeyless path prefix to auto-discover under. |
| `secrets` | Explicit `[{name, var}, ...]` mapping. |
| `var_name_template` | How to derive variable names from discovered paths. Default `{relpath}`. Other placeholders: `{basename}` (last segment) and `{fullname}` (full path). Non-identifier characters are replaced with `_`. |
| `secret_types` | Akeyless item types to discover. Default `['static-secret']`. |
| `hosts` | List of host names to attach variables to. |
| `groups` | Mapping of `group_name: [host, ...]`. Variables are attached at the group level. |
| `default_group` | Umbrella group containing every host or group created. Default `akeyless_managed`. |

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
