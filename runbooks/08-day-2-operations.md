# Day-2 Operations

This document covers ongoing operations after the integration is wired up:
secret rotation, adding and removing secrets, revoking access, and
refreshing the Execution Environment.

## Rotating a secret

1. Rotate the secret in Akeyless (CLI, console, or via your rotation
   workflow).
2. The next inventory sync picks up the new value. With
   **Update on launch** enabled on the inventory source (set in
   [step 06](06-inventory-source.md)), this happens automatically on the
   next job launch. No manual sync needed.
3. The next job that runs against the inventory uses the new value.

### Verify

Launch the smoke-test job from
[step 07](07-first-sync-and-job.md). The debug line's `length` (or
whatever non-leaking check you use) reflects the new value.

If you need a job to use the rotated value within seconds of rotation
rather than on next launch, click **Sync** on the inventory source
manually before launching the job. This is rarely needed.

## Adding a new secret

1. Create the secret under your `secret_path_prefix` in Akeyless. For
   example, with `secret_path_prefix: /apps/prod`, create
   `/apps/prod/redis/password`.
2. Confirm the same access role grants `read` on the new path. If you
   used a wildcard rule like `read on /apps/prod/*`, this is automatic.
3. The next inventory sync auto-discovers the secret. With the default
   `var_name_template: {relpath}`, it appears as the variable
   `redis_password` on every host.
4. New playbooks reference the variable by name. Existing playbooks
   remain unchanged.

### Verify

Trigger an inventory sync (or just launch any job, which fires the sync
when **Update on launch** is enabled). Open a host and confirm the new
variable is in the **Variables** panel.

## Removing a secret

1. Either delete the secret in Akeyless, or remove `read` on its path
   from the access role.
2. The next inventory sync drops the variable from the host_vars.

> **Warning:** Playbooks that still reference the removed variable will
> fail at runtime with `'<varname>' is undefined`. Search for usages
> before removing a widely-used secret. Consider replacing with a no-op
> default using `{{ var | default('') }}` if you need a soft removal.

## Revoking access (incident response)

If the cert and key pair backing the AWX credential is compromised,
revoke at either layer.

### Revoke the cert at the auth method (recommended)

In the Akeyless console, open the cert auth method, edit it, and either:

- Add the cert to the revocation list, or
- Rotate the CA the auth method trusts so the cert no longer chains.

Subsequent inventory syncs fail with a clear `401` from the SaaS API
before any job runs. No playbook executes with stale auth.

### Remove the role association

In the Akeyless console, open the access role, scroll to **Associated
Auth Methods**, and remove the cert auth method. Subsequent syncs
succeed in authenticating but `list_items` and `get_secret_value`
return empty or 403.

### Update the AWX credential

After issuing a new cert and binding it to the auth method, update the
credential instance (**Resources -> Credentials -> akeyless-prod-cert**)
with the new PEM material. Save. The next inventory sync uses the new
cert automatically.

## EE image refresh and pinning

The published reference EE
`ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:0.1.0` is rebuilt every Monday
at 09:00 UTC by `.github/workflows/ee-build.yml`. Each rebuild updates:

- The `:latest` and `:0.1.0` tags (moved to point at the new build).
- A new immutable `:weekly-YYYY-MM-DD` tag.

| Strategy | When to use | How |
|---|---|---|
| Track `:latest` | First-time tests, dev environments. | EE image: `ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:latest`, pull policy `always`. Picks up base image and transitive pip updates weekly. |
| Pin to `:0.1.0` | Most production environments. | EE image: `ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:0.1.0`. The tag still moves on rebuilds, but only within the 0.1.0 collection version. |
| Pin to a weekly tag | Strict supply-chain controls. | EE image: `ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:weekly-2026-04-21`. Immutable. Bump on a schedule you control. |
| Build your own | Air-gapped or internal-registry-only. | See [`03-execution-environment.md`](03-execution-environment.md) option B. |

### Bumping a pinned tag

1. Open the EE in **Administration -> Execution Environments**.
2. Update the **Image** field to the new tag.
3. Click **Save**.
4. The next inventory sync pulls the new image (because pull policy is
   `always`) and runs against it.

Trivy scans run daily on the published `:latest` tag, and SARIF is
uploaded to the GitHub Security tab of the repo. Subscribe to the
repository's security alerts if you want to be notified of new findings.

## Adding a second environment (staging, dev)

Reuse most of what you built. For each new environment:

1. Create a new cert and key pair in Akeyless (or reuse, if your trust
   model allows). Bind it to a separate role with `read` on the new
   environment's path prefix (for example `/apps/staging/*`).
2. Create a new credential instance of the same Custom Credential Type
   ([step 05](05-awx-credential-type.md)) and name it
   `akeyless-staging-cert`.
3. Add a second inventory YAML to the same project repo (for example
   `inventory.akeyless.staging.yml`) pointing at the new prefix:

   ```yaml
   plugin: akeyless.awx_integration.akeyless
   secret_path_prefix: /apps/staging
   hosts:
     - app01-staging.example.com
   default_group: staging_apps
   ```

4. Create a new Inventory and Inventory Source
   ([step 06](06-inventory-source.md)), wiring the new YAML to the new
   credential. Reuse the same EE.

The Custom Credential Type and the EE are shared across all
environments.

## Next steps

- [Troubleshooting](09-troubleshooting.md). Diagnoses for common failure modes.
