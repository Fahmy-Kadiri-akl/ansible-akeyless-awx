# Troubleshooting

Categorized failure modes for this integration, with diagnoses and fixes.

## Inventory sync fails with `ModuleNotFoundError: No module named 'akeyless'`

Diagnosis: the EE running the inventory sync does not contain the
`akeyless` Python SDK. AWX does not install project-level
`requirements.txt` for inventory updates, so this means the wrong EE is
in use.

Fix: confirm the **Execution Environment** field on the inventory
source (not the inventory itself, and not the system default) points
at the akeyless EE you registered in
[step 03](03-execution-environment.md).

Two places set the EE in AWX, and they are not equivalent:

| Setting | What it controls |
|---|---|
| Settings -> System -> default execution environment | Used as a fallback for jobs that don't have one set. Not used for inventory updates. |
| Inventory source -> Execution Environment | Used for the inventory update itself. This is the one that matters here. |

Set it on the source.

## Inventory sync fails with `401 Unauthorized` from Akeyless

Diagnosis: cert auth is failing inside the EE.

Steps to isolate:

1. Re-run the CLI verification from
   [`04-akeyless-cert-auth.md`](04-akeyless-cert-auth.md) from a shell
   on your laptop, with the same cert and key. If that fails too, the
   failure is in Akeyless, the cert, or the role. Fix it there before
   touching AWX again.
2. If the CLI succeeds but the AWX sync still fails:
   - Open the credential and confirm **Akeyless API URL** is
     `https://api.akeyless.io`, not a customer gateway URL. Customer
     gateway ingresses do not pass TLS client cert payloads through by
     default.
   - Confirm the credential's PEM payloads match what the CLI used.
     Re-paste if unsure. Copy errors are surprisingly common.
   - Confirm the cert is not expired.

## Inventory sync succeeds but no host_vars show up

Diagnosis: the plugin authenticated and called `list_items`, but the
result was empty. Usually one of:

- The access role does not grant `list` and `read` on
  `secret_path_prefix`.
- No items exist under that path.
- The items under that path are not of type `static-secret` (the
  default for `secret_types`).

Fix:

1. In the Akeyless console, open **Items** and navigate to the
   `secret_path_prefix` value. Confirm items exist there.
2. Open the access role bound to the cert auth method. Confirm it has a
   rule that grants `read` on that path (or a wildcard like
   `/apps/prod/*`).
3. If your items are dynamic or rotated rather than static, expand
   `secret_types` in the inventory YAML:

   ```yaml
   secret_types:
     - static-secret
     - dynamic-secret
     - rotated-secret
   ```

If all three checks pass and the sync still returns no host_vars,
capture the inventory-update job log (Jobs -> the failed inventory sync
-> Output) and look for the plugin's per-item log lines. They name
exactly which secrets the plugin tried to fetch and what response it
got.

## Job picks up an old secret value after rotation in Akeyless

Diagnosis: the inventory was synced before rotation and **Update on
launch** is not enabled, so AWX is using a cached inventory.

Fix: open the inventory source, enable **Update on launch**, and save.
The next job launch fires a sync first.

For one-off cases, click **Sync** on the source manually, then launch
the job.

## `awx-ee` is being used despite registering the akeyless EE

Diagnosis: the EE is set somewhere other than where AWX looks for
inventory updates. See the table in
[the ModuleNotFoundError section above](#inventory-sync-fails-with-modulenotfounderror-no-module-named-akeyless).
The system-wide default does not apply to inventory updates.

Fix: set the EE on the inventory source (Resources -> Inventories
-> open inventory -> Sources tab -> open source -> Execution
Environment).

## Project sync fails with "inventory file not found"

Diagnosis: the path you typed in the inventory source's
**Inventory file** field does not match the file in the Git repo. The
path is relative to the project root.

Fix: open the project's working directory in your local clone and
confirm the exact relative path of the YAML. Update the Inventory file
field to match.

## Inventory sync fails with `each 'secrets' entry must have 'name' and 'var' keys`

Diagnosis: the explicit `secrets:` mapping in the YAML is missing one
of the required keys.

Fix: every entry needs both:

```yaml
secrets:
  - name: /apps/prod/db_password   # required
    var: db_password               # required
```

## Inventory sync fails with `var_name_template uses unknown placeholder: ...`

Diagnosis: the `var_name_template` references a placeholder that isn't
supported. Only `{basename}`, `{relpath}`, and `{fullname}` exist.

Fix: rewrite the template using only those placeholders. Example:

```yaml
var_name_template: app_{basename}
```

## Variable name collision warnings in the sync log

Diagnosis: two distinct Akeyless paths normalize to the same variable
name. The plugin keeps the first one and warns about the second.

Example: `/apps/prod/db-password` and `/apps/prod/db_password` both
become `db_password`.

Fix: either rename the Akeyless secrets to be unambiguous, or fall
back to the explicit `secrets:` mode for the affected pair so each
gets a distinct `var`.

## Cert auth fails because the credential points at a customer gateway

Diagnosis: the credential's **Akeyless API URL** is something like
`https://your-gw:8000/api/v1`. Customer gateway ingresses do not, by
default, pass TLS client cert payloads through to the gateway pod, so
cert-auth handshakes fail there.

Fix: switch the URL to the SaaS API at `https://api.akeyless.io`. See
[`04-akeyless-cert-auth.md`](04-akeyless-cert-auth.md) for the
endpoint distinction in detail.

## EE image pull fails with "manifest unknown" or "unauthorized"

Diagnosis: the image tag does not exist on the registry, or the
registry requires authentication.

Fix:

- For the public reference image, confirm the tag matches one published
  in [GHCR](https://github.com/Fahmy-Kadiri-akl/ansible-akeyless-awx/pkgs/container/akeyless-awx-ee).
  Common typos: missing namespace, wrong case in `fahmy-kadiri-akl`.
- For private registries (option B in
  [`03-execution-environment.md`](03-execution-environment.md)), attach
  a registry credential to the Execution Environment in AWX.

## Where to look for plugin-side logs

When an AWX inventory sync runs, all of the inventory plugin's
`display` calls land in the inventory-update job's **Output** tab in
AWX. The plugin emits warnings for:

- Skipped duplicate variable names.
- Secrets that returned no value from the API.
- Secrets it could not derive a variable name for.

These are non-fatal. If the sync's overall status is `Successful` but
specific variables are missing, search the Output for `Akeyless:` to
see the per-item warnings.

## Still stuck

Open an issue at <https://github.com/Fahmy-Kadiri-akl/ansible-akeyless-awx/issues>
with:

1. AWX version (Settings -> About).
2. EE image tag in use.
3. The full **Output** of the failing inventory sync, with secret
   values redacted.
4. Whether the equivalent CLI cert-auth handshake from
   [`04-akeyless-cert-auth.md`](04-akeyless-cert-auth.md) succeeds from
   the same network.
