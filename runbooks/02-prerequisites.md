# Prerequisites

Complete every item in this checklist before starting. Most failures later
in this guide trace back to a missed prerequisite here.

## AWX / AAP

- [ ] AWX or AAP already deployed and reachable.
- [ ] You can log in with an account that has Administrator privileges.
      (You will create credential types, EEs, projects, inventories, and
      job templates.)

### Verify admin access

In the AWX UI, open the left-side menu and confirm you see
**Administration -> Credential Types** and **Administration -> Execution
Environments**. If those menu items are missing, your account does not
have the privileges this guide needs.

Or, via API:

```bash
AWX=https://<awx-host>
AUTH=admin:<password>
curl -sk -u "$AUTH" "$AWX/api/v2/me/" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin)["results"][0]; print("is_superuser:", d["is_superuser"])'
```

Expected: `is_superuser: True`. Anything else means you cannot create
the credential types and EEs the rest of this guide registers.

## Akeyless

- [ ] An Akeyless account (SaaS, or self-hosted with SaaS reachability).
- [ ] A cert auth method configured in Akeyless. Its access ID looks like
      `p-XXXXXXXXXXXXXX`. See the
      [Akeyless cert-auth documentation](https://docs.akeyless.io/docs/auth-with-certificate).
- [ ] An access role that grants `read` on the secret paths AWX will
      consume, with the cert auth method associated to it.
- [ ] A client certificate and private key issued by the CA the cert
      auth method trusts. Two PEM files in hand: cert and unencrypted key.
- [ ] At least one static secret exists under the path AWX will consume,
      so the first sync returns something.

### Verify the SaaS API is reachable from your AWX cluster

From any host that can shell into the AWX cluster:

```bash
curl -sI https://api.akeyless.io
```

Expected output (HTTP 405 is normal; this only tests TLS reachability):

```
HTTP/2 405
...
```

If this returns a network error, your AWX cluster cannot reach the
Akeyless SaaS API. Fix the network path before continuing. Every step
below depends on it.

### Verify the auth method exists

In the Akeyless console, open **Auth Methods** and filter by
**type = Certificate**. The access ID column shows the value you will use
as `AKEYLESS_ACCESS_ID`. Note it down.

Or, via CLI:

```bash
akeyless list-auth-methods --type cert
```

Expected: a JSON object with `auth_methods[]`; each entry has
`auth_method_name` and `auth_method_access_id` (a `p-...XXX` string).
Replace `--type cert` with `--type api_key` or `--type k8s` for the
other auth methods.

### Verify the role grants read on the right paths

In the Akeyless console, open the auth method, scroll to **Associated
Roles**, and click into the role. Confirm two things:

1. The role has a rule with `read` capability on the path AWX will consume
   (for example `/apps/prod/*`).
2. Items exist under that path.

Or, via CLI:

```bash
akeyless get-auth-method --name <auth-method-name>
```

Expected: the response includes an `auth_method_roles_assoc[]` array.
Each role's `rules.path_rules[]` entries list `path` and `capabilities`.
Look for a `path` that includes the prefix you plan to use (for example
`/apps/prod/*`) with `read` and `list` in `capabilities`.

To confirm items actually exist under that path, list them with a
short-lived token from a successful CLI handshake (see
[step 04](04-akeyless-auth.md)):

```bash
akeyless list-items --path /apps/prod --type static-secret --token t-...
```

Expected: a non-empty `items[]` array.

If either check fails, fix the role or seed at least one secret now.
The inventory plugin returns a clean error if items are missing, but a
misconfigured role usually surfaces as a 401 buried in an
inventory-update job log.

## Local tools

You need these only on your laptop (for CLI auth verification in
[step 04](04-akeyless-auth.md)) and on the machine that builds the EE
if you choose [option B in step 03](03-execution-environment.md).

- [ ] [`akeyless` CLI](https://docs.akeyless.io/docs/cli) installed.
- [ ] `docker` (or `podman`), only if you build your own EE image.
- [ ] [`ansible-builder`](https://ansible.readthedocs.io/projects/builder/en/latest/installation.html) v3.x, only if you build your own EE image.

### Verify `akeyless` CLI

```bash
akeyless --version
```

Expected output (CLI 1.139 or newer; the build hash on the right
varies):

```
Version: 1.139.0.fb23a68
```

## Information to gather

Collect the following before starting [step 04](04-akeyless-auth.md).
You will paste each into AWX during steps 4 to 6.

| Parameter | Description | Example |
|---|---|---|
| `akeyless_api_url` | Akeyless SaaS API URL. Almost always the default. | `https://api.akeyless.io` |
| `access_id` | Access ID of the cert auth method. | `p-XXXXXXXXXXXXXX` |
| `client_cert_pem_path` | Local filesystem path to the client cert PEM. | `/path/to/client.crt` |
| `client_key_pem_path` | Local filesystem path to the unencrypted private key PEM. | `/path/to/client.key` |
| `secret_path_prefix` | Akeyless path under which AWX-consumable secrets live. | `/apps/prod` |
| `awx_org` | AWX Organization that will own the credential, project, inventory, and template. | `Default` |

The credential's PEM payloads must not have trailing whitespace inside the
BEGIN/END headers, and the key must be unencrypted (no passphrase). The
fastest way to validate is the CLI handshake in
[step 04](04-akeyless-auth.md).

## Next steps

- [Execution Environment](03-execution-environment.md). Pick or build the EE that runs the inventory plugin.
