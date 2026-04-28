# Akeyless Cert-Auth Verification

The most common failure mode in this whole guide is "cert auth doesn't
actually work, but no error surfaces until the inventory plugin runs and
returns 401." Catch it now, with the CLI, before AWX is in the picture.

## Endpoint terminology (read this first)

Two distinct Akeyless endpoints exist, and they are **not** interchangeable
for cert auth.

| Endpoint | URL | Use for cert auth? |
|---|---|---|
| **Akeyless SaaS API** | `https://api.akeyless.io` | **Yes.** Cert-auth handshakes must terminate here. |
| **Customer gateway (self-hosted)** | e.g. `https://your-gateway.example.com:8000/api/v1` | **No.** Most customer gateway ingresses terminate TLS at the edge and do not forward TLS client certs through to the gateway pod, so cert-auth handshakes fail there. |

The AWX credential type defaults to the SaaS endpoint for this reason. Do not
"helpfully" change it to a gateway URL.

## How the `akeyless` CLI picks an endpoint

Verified against `akeyless` CLI 1.142.0. Cert auth has no `--gateway-url`
flag of its own, so the URL is determined entirely by env var + profile, in
this order:

1. `AKEYLESS_GATEWAY_URL` env var. If set, all calls route through it.
2. The active profile's `gateway_url` field, stored in
   `~/.akeyless/profiles/<profile>.toml`. Set or cleared via
   `akeyless configure --gateway-url <url>` (use `""` to clear).
3. Default: the Akeyless SaaS API.

For cert-auth verification both 1 and 2 must be empty so the CLI reaches the
SaaS API directly.

### Inspect the active profile

```bash
cat ~/.akeyless/profiles/default.toml
```

**Expected output (look for `gateway_url = ''`):**

```toml
access_id = 'p-XXXXXXXXXXXXXX'
access_key = ''
access_type = 'access_key'
gateway_url = ''
...
```

If `gateway_url` is set to anything other than `''`, clear it:

```bash
akeyless configure --gateway-url ""
```

## Verify with the CLI

From any machine that has the cert and key. The `env -u` clears any inherited
`AKEYLESS_GATEWAY_URL` so the CLI falls back to the profile or SaaS default:

```bash
env -u AKEYLESS_GATEWAY_URL akeyless auth \
  --access-id p-XXXXXXXXXXXXXX \
  --access-type cert \
  --cert-file-name /path/to/client.crt \
  --key-file-name /path/to/client.key
```

**Expected output:**

```
Authentication succeeded.
{"token":"t-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}
```

The presence of a `t-…` token is the only signal that cert auth works
end to end.

### Verify the token can actually fetch a secret

A token-only success does not prove the role grants what AWX needs. List one
secret under your intended `secret_path_prefix`:

```bash
env -u AKEYLESS_GATEWAY_URL akeyless list-items \
  --path /apps/prod \
  --type static-secret \
  --token t-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Expected output:**

```json
{
  "items": [
    { "item_name": "/apps/prod/db/password", "item_type": "STATIC_SECRET", ... },
    ...
  ]
}
```

If the items list is empty but you know secrets exist, the role bound to the
auth method does not grant `list` / `read` on `/apps/prod`. Fix the role
before continuing.

## Failure modes

| Error | Diagnosis |
|---|---|
| `failed to read certificate: open <path>: no such file or directory` | The path is wrong or the file is unreadable. |
| `failed to get credentials: failed to parse private key` | The key PEM is malformed or encrypted. Re-export an unencrypted key. |
| `Unauthorized via gateway: https://...` | The CLI routed through a customer gateway whose ingress is not forwarding TLS client certs (the gateway URL is echoed back in the error). Either `AKEYLESS_GATEWAY_URL` is still set or the profile has a `gateway_url`. Re-run with `env -u AKEYLESS_GATEWAY_URL` and clear the profile setting. |
| `unauthorized: certificate not allowed` / TLS handshake error from the SaaS | The cert was not issued by the CA the auth method trusts, or the cert has expired. |
| `unauthorized: missing role` | The auth method is not bound to a role that grants `read` on the path AWX will consume. |

Resolve any failure here before continuing. Do not try to debug cert auth
once it is buried inside an AWX inventory sync log — the AWX surface only
shows you a 401, not which of the above caused it.

## Next steps

- [AWX Custom Credential Type](05-awx-credential-type.md) — register the credential type and create a credential of that type using the cert and key you just verified.
