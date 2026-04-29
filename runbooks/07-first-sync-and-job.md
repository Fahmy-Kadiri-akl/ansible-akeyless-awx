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
  [step 04](04-akeyless-auth.md) no longer works once routed through
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

This step proves the *whole* picture works: a playbook with **zero
Akeyless code** in it can read the secrets that the inventory sync
attached as host_vars.

### 3a. Pick the playbook

A smoke-test playbook is already committed in this repo at
`examples/smoke_test.yml`. If your AWX project points at this repo,
just use that path. Skip ahead to 3b.

If you want to write your own (or your project is a different repo),
commit a file like this and push:

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

Notice what is not in this playbook: no `akeyless auth`, no
`get_secret_value` lookup, no cert handling. The secret is a plain
`host_var`.

`connection: local` is set because the example hosts in
`examples/inventory.akeyless.yml` (`app01.example.com`,
`app02.example.com`) are fictional placeholders. Real inventories
pointing at reachable targets do not need the `connection: local`
line; drop it for production.

### 3b. Create the Job Template

In the UI: **Resources -> Templates -> Add -> Job Template**.

| Field | Value |
|---|---|
| **Name** | `Akeyless smoke test`. |
| **Inventory** | `akeyless-prod` (from [step 06](06-inventory-source.md)). |
| **Project** | The project from [step 06](06-inventory-source.md). |
| **Playbook** | `examples/smoke_test.yml` (or your own playbook path if you wrote one in 3a). |
| **Execution Environment** | The EE from [step 03](03-execution-environment.md). |
| **Credentials** | The credential from [step 05](05-awx-credential-type.md). Required for the inventory sync that fires on launch. |

Click **Save**.

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

echo "JT_ID=$JT_ID"
```

### 3c. Launch the job

In the UI: open the Job Template you just created and click **Launch**
(rocket icon).

Or, via API:

```bash
JOB_ID=$(curl -sk -u "$AUTH" -X POST "$AWX/api/v2/job_templates/$JT_ID/launch/" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "JOB_ID=$JOB_ID"
```

### 3d. Verify

The job needs to **complete with `Successful` status** AND the playbook
output needs to show that each host actually saw a non-zero
host_var count. Both conditions are required; status `Successful` on
its own only proves the play didn't throw, not that the secrets
arrived.

#### Watch the job from the UI

In the UI: **Views -> Jobs**, click into your job. The Output tab
streams the live stdout. When it finishes, the bar at the top turns
green and the **Status** field shows `Successful`. Scroll to the bottom
of Output for `PLAY RECAP`.

#### Or watch from the API

```bash
# Poll status until it's terminal
while true; do
  s=$(curl -sk -u "$AUTH" "$AWX/api/v2/jobs/$JOB_ID/" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  echo "  status=$s"
  case "$s" in successful|failed|error|canceled) break;; esac
  sleep 5
done

# Once it's successful, fetch the rendered output
curl -sk -u "$AUTH" "$AWX/api/v2/jobs/$JOB_ID/stdout/?format=txt"
```

#### What success looks like

With `examples/smoke_test.yml`, the tail of the output is:

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

What to check:

1. **`PLAY RECAP` shows `ok=2`** for every host. `ok=2` means the
   `assert` task (which fails if no Akeyless host_var arrived) passed,
   AND the debug task ran. `ok=1` would mean assert passed but debug
   skipped, usually a YAML typo. `failed=1` on the assert task means
   no host_vars made it to the play.
2. **The "Akeyless secrets reached the playbook as host_vars" line
   appears once per host**. If it does not appear at all, the assert
   didn't run, which means the play targeted no hosts (check the
   `hosts: all` line in the smoke playbook).
3. **The variable count is greater than ~30**. The plugin adds one
   variable per discovered Akeyless secret on top of Ansible's built-in
   ~30 (`group_names`, `inventory_hostname`, `play_hosts`, etc.). With
   the seeded `/apps/prod/` data, expect 55 to 60.

#### Confirm a specific secret value reached the play

The smoke test proves the host_vars *arrived*. To prove a specific
secret value is *correct*, compare lengths between Akeyless and the
playbook's view (without printing the actual value):

```bash
# Length seen by the playbook (admin-only API):
curl -sk -u "$AUTH" "$AWX/api/v2/hosts/$HOST_ID/variable_data/" \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["db_password"]))'

# Length stored in Akeyless:
TOK=$(env -u AKEYLESS_GATEWAY_URL akeyless auth \
  --access-id <ID> --access-type <cert|access_key|k8s> --json ... \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
env -u AKEYLESS_GATEWAY_URL akeyless get-secret-value \
  --name /apps/prod/db_password --token "$TOK" \
  | wc -c
```

The two numbers should match (give or take a trailing newline from
`wc -c`). If they match for one secret, the plugin is fetching values
correctly and not corrupting them.

Never print the secret value in playbook output. Use `| length` or
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
