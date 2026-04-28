# First Sync and Test Job

This step exercises the full path end to end:

1. Run the inventory sync and confirm it succeeds.
2. Inspect the discovered host_vars in the AWX UI.
3. Run a playbook against the inventory and confirm a secret reaches the
   play as an ordinary variable, with no Akeyless-aware code.

## Step 1: trigger the inventory sync

In the inventory's **Sources** tab, click the sync icon next to the
`akeyless` source.

Or, via API:

```bash
AWX=https://<awx-host>
AUTH="admin:<password>"
SRC_ID=...   # from step 06

curl -sk -u "$AUTH" -X POST "$AWX/api/v2/inventory_sources/$SRC_ID/update/" \
  | python3 -c 'import json,sys; print("inventory_update id:", json.load(sys.stdin).get("inventory_update"))'
```

### Verify

The sync transitions through `Pending`, `Running`, and `Successful`
within about 30 seconds (longer the first time if the EE is being
pulled).

If it fails, jump to [`09-troubleshooting.md`](09-troubleshooting.md).
The two most common first-time failures are:

- `ModuleNotFoundError: No module named 'akeyless'`. The wrong EE is on
  the source.
- `401 Unauthorized`. Cert auth that worked in
  [step 04](04-akeyless-cert-auth.md) no longer works once routed through
  AWX. Almost always: the credential's **Akeyless API URL** is a customer
  gateway URL instead of `https://api.akeyless.io`.

## Step 2: inspect the discovered host_vars

In the inventory, open the **Hosts** tab. The hosts you listed in the
YAML's `hosts:` (or under `groups:`) appear here.

Click any host. In the right-hand **Variables** panel you should see one
variable per discovered Akeyless secret. With the example
`secret_path_prefix: /apps/prod` from
[step 06](06-inventory-source.md), a secret at `/apps/prod/db_password`
becomes a variable named `db_password`.

Or, via API:

```bash
HOST_ID=$(curl -sk -u "$AUTH" "$AWX/api/v2/inventories/$INV_ID/hosts/?name=app01.example.com" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["results"][0]["id"])')
curl -sk -u "$AUTH" "$AWX/api/v2/hosts/$HOST_ID/variable_data/"
```

Expected (variable names follow your `secret_path_prefix` content; the
example here matches the secrets seeded under `/apps/prod/`):

```json
{
  "api_token": "...",
  "aws_access_key": "...",
  "datadog_api_key": "...",
  "db_password": "...",
  "jenkins_pat": "...",
  "slack_webhook": "..."
}
```

In the UI the values are masked as `$encrypted$`. The API returns them
in plaintext to admins; see the security note at the bottom of this
document.

### Verify there are no surprises

- Every secret you expect under `secret_path_prefix` is here. If some are
  missing, the access role does not grant `read` on them, or they are
  not of `static-secret` type. See
  [`09-troubleshooting.md`](09-troubleshooting.md#inventory-sync-succeeds-but-no-host_vars-show-up).
- No variable has an empty or unmasked value. Empty values mean the
  secret exists but the read returned no data; check the secret's value
  in Akeyless.

Variable name collisions: if two distinct Akeyless paths normalize to the
same variable name (for example `/apps/prod/db-password` and
`/apps/prod/db_password` both become `db_password`), the second one is
dropped with a warning in the inventory-sync log. Either rename the
Akeyless secrets or use the explicit `secrets:` mapping mode for those
two.

## Step 3: run a playbook that consumes a secret

### Use the example playbook in this repo

If your AWX project points at this repo, a smoke-test playbook is
already committed at `examples/smoke_test.yml`. Use it directly with
the **Playbook** field set to `examples/smoke_test.yml`.

### Or, write your own

```yaml
# example_playbook.yml
- name: Use an Akeyless-sourced secret as an ordinary host_var
  hosts: prod_apps
  gather_facts: false
  connection: local
  tasks:
    - name: Show the variable was injected (length only, never print values)
      ansible.builtin.debug:
        msg: "{{ inventory_hostname }} sees db_password of length {{ db_password | length }}"
```

Notice what is not in this playbook: no `akeyless login`, no
`get_secret_value` lookup, no cert handling. The secret is a plain
`host_var`.

`connection: local` is set because the example hosts in
`examples/inventory.akeyless.yml` (`app01.example.com`,
`app02.example.com`) are fictional placeholders. Real inventories
pointing at reachable targets do not need the `connection: local`
line; drop it for production.

Commit and push.

### Create a Job Template

Navigate: **Resources -> Templates -> Add -> Job Template**.

| Field | Value |
|---|---|
| **Name** | `Akeyless smoke test`. |
| **Inventory** | `akeyless-prod` (from [step 06](06-inventory-source.md)). |
| **Project** | The project from [step 06](06-inventory-source.md). |
| **Playbook** | `examples/smoke_test.yml` (or your own playbook path if you wrote one). |
| **Execution Environment** | The EE from [step 03](03-execution-environment.md). |
| **Credentials** | The credential from [step 05](05-awx-credential-type.md). Required for the inventory sync that fires on launch. |

Click **Save**, then **Launch**.

Or, via API:

```bash
JT_ID=$(curl -sk -u "$AUTH" -H 'Content-Type: application/json' \
  -X POST "$AWX/api/v2/job_templates/" \
  -d "{
    \"name\":\"Akeyless smoke test\",
    \"job_type\":\"run\",
    \"inventory\":$INV_ID,
    \"project\":$PROJECT_ID,
    \"playbook\":\"examples/smoke_test.yml\",
    \"execution_environment\":$EE_ID
  }" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

# Attach the credential (required for the launch-time inventory sync)
curl -sk -u "$AUTH" -H 'Content-Type: application/json' \
  -X POST "$AWX/api/v2/job_templates/$JT_ID/credentials/" \
  -d "{\"id\":$CREDENTIAL_ID}"

# Launch
curl -sk -u "$AUTH" -X POST "$AWX/api/v2/job_templates/$JT_ID/launch/"
```

### Verify

The job completes with `Successful` status. With
`examples/smoke_test.yml`, the output is:

```
PLAY [Smoke test for Akeyless inventory plugin] ********************************

TASK [Confirm at least one Akeyless-sourced host_var is present] ***************
ok: [app01.example.com] => {"msg": "Akeyless secrets reached the playbook as host_vars"}
ok: [app02.example.com] => {"msg": "Akeyless secrets reached the playbook as host_vars"}

TASK [Show variable name count (never print values)] ***************************
ok: [app01.example.com] => {"msg": "app01.example.com has 55 variables"}
ok: [app02.example.com] => {"msg": "app02.example.com has 55 variables"}

PLAY RECAP *********************************************************************
app01.example.com          : ok=2    changed=0    unreachable=0    failed=0
app02.example.com          : ok=2    changed=0    unreachable=0    failed=0
```

The variable count includes Ansible-supplied vars (`group_names`,
`inventory_hostname`, etc.) plus the ones the plugin attached. Both
hosts having `ok=2` means the assert passed and the debug ran.

Never print secret values in playbook output. Use `| length` or
`| hash('sha256') | truncate(8, true, '')` to confirm presence without
leaking the value into job logs.

## A note on visibility of secret values

AWX masks `key_data` and host-variable secret values in the UI. It
does **not** encrypt host-variable values at rest in the way it does
credential secrets. AWX administrators can read every host_var in
plaintext via the API:

```bash
GET /api/v2/hosts/<id>/variable_data/
```

Treat this the same as any other admin-tier capability: the protection
boundary is "who is an AWX admin," not "values are encrypted." Limit
who has admin or organization-admin roles, and prefer Akeyless-side
role scoping (one access role per environment) so a compromised AWX
admin cannot reach beyond the access role's path prefix.

## What you have at this point

- Akeyless secrets land as ordinary `host_vars` on every inventory sync.
- Adding or rotating a secret in Akeyless takes effect on the next sync,
  with no AWX or playbook change.
- Playbooks reference secrets by their AWX-side variable name. They
  contain no Akeyless code, no cert paths, and no auth logic.

## Next steps

- [Day-2 operations](08-day-2-operations.md). Rotation, adding and removing secrets, revocation, EE refresh and pinning.
