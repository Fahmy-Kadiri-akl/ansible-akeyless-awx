# First Sync and Test Job

This step exercises the full path end to end:

1. Run the inventory sync and confirm it succeeds.
2. Inspect the discovered host_vars in the AWX UI.
3. Run a playbook against the inventory and confirm a secret reaches the
   play as an ordinary variable, with no Akeyless-aware code.

## Step 1: trigger the inventory sync

In the inventory's **Sources** tab, click the sync icon next to the
`akeyless` source.

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
[step 06](06-inventory-source.md), a secret at `/apps/prod/db/password`
becomes a variable named `db_password`.

Expected example variables panel (values masked by AWX):

```yaml
db_password: $encrypted$
api_token: $encrypted$
smtp_password: $encrypted$
```

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
| **Playbook** | `example_playbook.yml`. |
| **Execution Environment** | The EE from [step 03](03-execution-environment.md). |
| **Credentials** | The credential from [step 05](05-awx-credential-type.md). Required for the inventory sync that fires on launch. |

Click **Save**, then **Launch**.

### Verify

The job completes with `Successful` status. The output shows one debug
line per host:

```
TASK [Show the variable was injected (length only, never print values)] *******
ok: [app01.example.com] => {
    "msg": "app01.example.com sees db_password of length 24"
}
ok: [app02.example.com] => {
    "msg": "app02.example.com sees db_password of length 24"
}
```

If you see the debug line and the length matches the secret's value, the
integration is wired correctly end to end.

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
