# Prerequisites

Complete every item in this checklist before starting. Most failures later in
this guide trace back to a missed prerequisite here.

## AWX / AAP

- [ ] AWX or AAP already deployed and reachable.
- [ ] You can log in with an account that has **Administrator** privileges
      (you will create credential types, EEs, projects, inventories, and job
      templates).

### Verify admin access

In the AWX UI, open the left-side menu and confirm you see
**Administration -> Credential Types** and **Administration -> Execution
Environments**. If those menu items are missing, your account does not have
the privileges this guide needs.

## Akeyless

- [ ] An Akeyless account (SaaS or self-hosted with SaaS reachability).
- [ ] A **cert auth method** configured in Akeyless. Its access ID looks like
      `p-XXXXXXXXXXXXXX`. See the
      [Akeyless cert-auth documentation](https://docs.akeyless.io/docs/auth-with-certificate).
- [ ] An **access role** that grants `read` on the secret paths AWX will
      consume, with the cert auth method associated to it.
- [ ] A **client certificate and private key** issued by the CA the cert
      auth method trusts. Two PEM files in hand: cert and unencrypted key.
- [ ] At least one **static secret** exists under the path AWX will consume
      (for the first sync to return anything).

### Verify the SaaS API is reachable from your AWX cluster

From any host that can shell into the AWX cluster:

```bash
curl -sI https://api.akeyless.io
```

**Expected output (HTTP 405 is normal — we are only testing TLS reachability):**

```
HTTP/2 405
...
```

If this returns a network error, your AWX cluster cannot reach the Akeyless
SaaS API. Fix the network path before continuing — every step below depends on
this.

### Verify the auth method exists

In the Akeyless console, open **Auth Methods** and filter by **type =
Certificate**. The access ID column shows the value you will use as
`AKEYLESS_ACCESS_ID`. Note it down.

### Verify the role grants read on the right paths

In the Akeyless console, open the auth method, scroll to **Associated
Roles**, and click into the role. Confirm:

1. The role has a rule with `read` capability on the path AWX will consume
   (for example `/apps/prod/*`).
2. There exist items under that path.

If either is false, fix it now. The inventory plugin returns a clean error if
items are missing, but a misconfigured role usually surfaces as a 401 buried
in an inventory-update job log.

## Local tools

You need these only on your laptop (for cert-auth verification in
[step 04](04-akeyless-cert-auth.md)) and on the machine that builds the EE if
you choose [option B in step 03](03-execution-environment.md).

- [ ] [`akeyless` CLI](https://docs.akeyless.io/docs/cli) installed.
- [ ] `docker` (or `podman`) — only if you build your own EE image.
- [ ] [`ansible-builder`](https://ansible.readthedocs.io/projects/builder/en/latest/installation.html) v3.x — only if you build your own EE image.

### Verify `akeyless` CLI

```bash
akeyless --version
```

**Expected output (any 1.14x.x or newer is fine):**

```
1.142.0
```

## Information to gather

Collect the following before starting [step 04](04-akeyless-cert-auth.md). You
will paste each into AWX during steps 4–6.

| Parameter | Description | Example |
|---|---|---|
| `akeyless_api_url` | Akeyless SaaS API URL. Almost always the default. | `https://api.akeyless.io` |
| `access_id` | Access ID of the cert auth method | `p-XXXXXXXXXXXXXX` |
| `client_cert_pem_path` | Local filesystem path to the client cert PEM | `/path/to/client.crt` |
| `client_key_pem_path` | Local filesystem path to the unencrypted private key PEM | `/path/to/client.key` |
| `secret_path_prefix` | Akeyless path under which AWX-consumable secrets live | `/apps/prod` |
| `awx_org` | AWX Organization that will own the credential, project, inventory, and template | `Default` |

> **Tip:** The credential's PEM payloads must not have trailing whitespace
> inside the BEGIN/END headers, and the key must be unencrypted (no
> passphrase). The fastest way to validate is the CLI handshake in
> [step 04](04-akeyless-cert-auth.md).

## Next steps

- [Execution Environment](03-execution-environment.md) — pick or build the EE that runs the inventory plugin.
