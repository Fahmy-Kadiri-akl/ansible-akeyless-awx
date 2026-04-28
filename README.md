# akeyless.awx_integration

Ansible Collection that wires Akeyless secrets into AWX/AAP at the platform
level so playbooks consume them as ordinary Ansible variables. No login
tasks, no lookup expressions, no Akeyless code in any playbook.

## What problem this solves

Customers operating hundreds of playbooks against Akeyless typically embed
explicit `akeyless login` and `akeyless get-secret-value` tasks inside
every play. That couples every playbook to Akeyless, multiplies the
maintenance surface, and makes credential rotation or secret addition
expensive.

This collection moves the integration up one layer:

- **Authentication** lives in an AWX Custom Credential Type, configured
  once.
- **Secret retrieval** runs at inventory-sync time via an Ansible Inventory
  Plugin and lands as host_vars / group_vars.
- **Adding a new secret** in Akeyless makes it appear as a new variable on
  the next inventory sync, with no AWX-side or playbook-side change.
- **Rotating an existing secret** propagates on the next sync, again with
  no AWX-side or playbook-side change.

## Components

| Component | Path | Purpose |
|---|---|---|
| Inventory plugin | `plugins/inventory/akeyless.py` | Authenticates to Akeyless, fetches secrets, attaches them to hosts/groups as Ansible variables. Supports either path-prefix discovery (recommended) or an explicit name-to-var mapping. |
| AWX Custom Credential Type | `extensions/awx/credential_types/akeyless_cert_auth.yml` | Defines a reusable credential type whose injectors write the cert/key to tempfiles and expose env vars consumed by the plugin. |
| EE build context | `ee/` | An ansible-builder context that adds the akeyless Python SDK and this collection to your existing AWX Execution Environment image. |

## Requirements

- AWX or AAP already deployed and reachable.
- Akeyless already deployed (SaaS or self-hosted gateway).
- A cert-auth method configured in Akeyless, with an access role granting
  read on the secret paths AWX will consume. (See the
  [Akeyless cert-auth docs](https://docs.akeyless.io/docs/auth-with-certificate).)
- A custom Execution Environment that includes this collection,
  `akeyless.secrets_management` from Galaxy, and the `akeyless` Python SDK.
  AWX does not auto-install project-level Python deps for inventory updates,
  so the SDK must be baked into the EE.

## Get started

End-to-end setup, including Akeyless cert-auth verification, EE selection,
credential-type creation, inventory source configuration, first-sync
verification, day-2 operations, and troubleshooting, is documented in
[`runbooks/awx-setup.md`](runbooks/awx-setup.md).

A reference Execution Environment is published on GHCR for users who want
to skip the build step:

```
ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:0.1.0
```

It contains this collection, `akeyless.secrets_management`, and the
`akeyless` Python SDK. Rebuilt weekly. Public; pulls require no auth.

## Inventory plugin options

| Option | Purpose |
|---|---|
| `secret_path_prefix` | Auto-discover every static secret under this path. New secrets added in Akeyless show up automatically on the next sync. |
| `secrets` | Explicit `{name, var}` mapping when a fixed naming contract is needed. Combinable with `secret_path_prefix`. |
| `var_name_template` | How to derive variable names from secret paths. Defaults to the path under the prefix with `/` replaced by `_`. Other placeholders: `{basename}`, `{fullname}`. |
| `secret_types` | Akeyless item types to discover. Default: `['static-secret']`. |
| `hosts` / `groups` / `default_group` | Where to attach the discovered variables. |

Auth options (`access_id`, `cert_file`, `key_file`, `access_type`,
`akeyless_api_url`) are normally injected by the AWX credential and do not
need to live in the inventory source YAML.

## Why an inventory plugin instead of a credential plugin?

AWX's first-class "Credential Plugin" / "External Secret Management Source"
mechanism (the one used by HashiCorp Vault, CyberArk, etc.) requires
modifications to AWX itself. The AWX upstream is in a refactor and not
accepting new credential plugins as of 2024-07. An inventory plugin
combined with a Custom Credential Type achieves the same end-state
(platform-level auth, no playbook changes, dynamic secret pickup) without
depending on the frozen upstream.

## Maintenance and supply-chain hygiene

Two GitHub Actions workflows (`.github/workflows/ee-build.yml` and
`ee-scan.yml`) keep the published EE image fresh and visibly scanned.
`ee-build.yml` rebuilds weekly (Mondays 09:00 UTC) and on dependency
changes; `ee-scan.yml` runs Trivy daily and uploads SARIF to the GitHub
Security tab. Both are non-blocking by default; flip the scan step's
`exit-code: 1` to gate CI on findings.

## Versions and compatibility

- Tested against AWX 24.6.1 with the default `awx-ee` execution environment
  (Python 3.12, ansible-core 2.18).
- Depends on `akeyless.secrets_management` >= 1.0.0 from Ansible Galaxy.
- Requires the akeyless Python SDK >= 5.0.

## Releasing to Ansible Galaxy

The `akeyless` namespace on Galaxy is controlled by Akeyless and already
publishes `akeyless.secrets_management`. Releasing a new version of this
collection under that namespace requires being a maintainer of the
namespace, so coordinate internally before tagging a release. Once
approved:

1. Bump `version` in `galaxy.yml`.
2. Tag and push:

   ```bash
   git tag -a v0.1.0 -m "akeyless.awx_integration v0.1.0"
   git push origin main --tags
   ```

3. Build the artifact:

   ```bash
   ansible-galaxy collection build --output-path ./dist .
   ```

4. Publish (API key from <https://galaxy.ansible.com/ui/token/>):

   ```bash
   ansible-galaxy collection publish \
     ./dist/akeyless-awx_integration-0.1.0.tar.gz \
     --api-key "$GALAXY_API_KEY"
   ```

5. Consumers install via:

   ```yaml
   collections:
     - name: akeyless.awx_integration
       version: ">=0.1.0"
   ```

Until a Galaxy version is cut, install directly from Git:

```yaml
collections:
  - name: https://github.com/Fahmy-Kadiri-akl/ansible-akeyless-awx.git
    type: git
    version: main
```

Pin to a tag (`version: v0.1.0`) once one exists.

## License

MIT
