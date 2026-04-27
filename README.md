# akeyless.awx_integration

Ansible Collection that wires Akeyless secrets into AWX/AAP at the **platform
level** so playbooks consume them as ordinary Ansible variables. No login
tasks, no lookup expressions, no Akeyless code in any playbook.

## What problem this solves

Customers operating hundreds of playbooks against Akeyless typically embed
explicit `akeyless login` and `akeyless get-secret-value` tasks inside every
play. That couples every playbook to Akeyless, multiplies the maintenance
surface, and makes credential rotation or secret addition expensive.

This collection moves the integration up one layer:

- **Authentication** lives in an AWX Custom Credential Type, configured once.
- **Secret retrieval** runs at inventory-sync time via an Ansible Inventory
  Plugin and lands as host_vars / group_vars.
- **Adding a new secret** in Akeyless makes it appear as a new variable on
  the next inventory sync, with no AWX-side or playbook-side change.
- **Rotating an existing secret** propagates on the next sync, again with no
  AWX-side or playbook-side change.

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
  read on the secret paths AWX will consume. (See
  [Akeyless docs](https://docs.akeyless.io/docs/auth-with-certificate).)
- A custom Execution Environment that includes this collection,
  `akeyless.secrets_management` from Galaxy, and the akeyless Python SDK.
  AWX does not auto-install project-level Python deps for inventory updates,
  so the SDK must be baked into the EE.

## Quick start

1. Use the published reference Execution Environment image:

   ```
   ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:0.1.0
   ```

   It is built on `quay.io/ansible/awx-ee:latest` and contains this
   collection, `akeyless.secrets_management`, and the `akeyless` Python
   SDK. The package is public; pulls do not require authentication.

   For environments that require a private/internal registry, the same
   artifact can be reproduced from the `ee/` directory in this repo:

   ```bash
   cd ee
   ansible-builder build -t your-registry.example/akeyless-awx-ee:0.1.0 \
     -f execution-environment.yml --container-runtime docker
   docker push your-registry.example/akeyless-awx-ee:0.1.0
   ```

2. Register the EE in AWX (Settings -> Execution Environments). Use the
   GHCR image above directly, or the image you pushed.

3. Create the Custom Credential Type from
   `extensions/awx/credential_types/akeyless_cert_auth.yml` (System
   Administration -> Credential Types).

4. Create a credential of that type with your Akeyless access ID and PEM
   cert/key issued by the trusted CA.

5. Create or pick a Project (any SCM) that contains an inventory source
   YAML, e.g.:

   ```yaml
   # inventory.akeyless.yml
   plugin: akeyless.awx_integration.akeyless
   secret_path_prefix: /apps/prod
   hosts:
     - app01.example.com
     - app02.example.com
   default_group: prod_apps
   ```

6. Create an Inventory Source pointing at that YAML, attach the credential
   from step 4, enable 'Update on launch'.

7. Reference the Inventory in any Job Template. Existing playbooks consume
   the discovered secrets as ordinary host_vars; no playbook code changes.

See `docs/awx-setup.md` for the full walkthrough.

## Inventory plugin options

| Option | Purpose |
|---|---|
| `secret_path_prefix` | Auto-discover every static secret under this path. New secrets added in Akeyless show up automatically on the next sync. |
| `secrets` | Explicit `{name, var}` mapping when you want a fixed contract. Combinable with `secret_path_prefix`. |
| `var_name_template` | How to derive variable names from secret paths. Defaults to the path under the prefix with C(/) -> C(_). Other placeholders: `{basename}`, `{fullname}`. |
| `secret_types` | Akeyless item types to discover. Default: `['static-secret']`. |
| `hosts` / `groups` / `default_group` | Where to attach the discovered variables. |

Auth options (`access_id`, `cert_file`, `key_file`, `access_type`,
`akeyless_api_url`) are normally injected by the AWX credential and do not
need to live in the inventory source YAML.

## Why an inventory plugin instead of a credential plugin?

AWX's first-class 'Credential Plugin' / 'External Secret Management Source'
mechanism (the one used by HashiCorp Vault, CyberArk, etc.) requires
modifications to AWX itself. The AWX upstream is in a refactor and not
accepting new credential plugins as of 2024-07. An inventory plugin combined
with a Custom Credential Type achieves the same end-state (platform-level
auth, no playbook changes, dynamic secret pickup) without depending on the
frozen upstream.

## Versions and compatibility

- Tested against AWX 24.6.1 with default `awx-ee` execution environment
  (Python 3.12, ansible-core 2.18).
- Depends on `akeyless.secrets_management` >= 1.0.0 from Ansible Galaxy.
- Requires the akeyless Python SDK >= 5.0.

## Releasing to Ansible Galaxy

The `akeyless` namespace on Galaxy is controlled by Akeyless and already
publishes `akeyless.secrets_management`. Releasing a new version of this
collection under that namespace requires being a maintainer of the
namespace, so coordinate internally before tagging a release. The release
flow once approved:

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

4. Publish to Galaxy with an API key from
   <https://galaxy.ansible.com/ui/token/>:

   ```bash
   ansible-galaxy collection publish \
     ./dist/akeyless-awx_integration-0.1.0.tar.gz \
     --api-key "$GALAXY_API_KEY"
   ```

5. After publishing, consumers install with:

   ```yaml
   # collections/requirements.yml
   collections:
     - name: akeyless.awx_integration
       version: ">=0.1.0"
   ```

### Installing before a Galaxy release is cut

Until a version is on Galaxy, customers can install directly from Git via
their project's `collections/requirements.yml`:

```yaml
collections:
  - name: https://github.com/Fahmy-Kadiri-akl/ansible-akeyless-awx.git
    type: git
    version: main
```

Pin to a tag (`version: v0.1.0`) once one exists.

## License

MIT
