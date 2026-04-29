# Akeyless Authentication Verification

The most common failure mode in this guide is "auth doesn't actually work,
but no error surfaces until the inventory plugin runs and returns 401."
Catch it now, with the CLI, before AWX is in the picture.

The collection ships three Custom Credential Types covering three auth
methods. Pick one and verify it works on its own before you wire it into
AWX.

| Auth method | Use it when | Credential Type |
|---|---|---|
| **Cert** | Long-lived TLS client cert + key issued by a CA the Akeyless auth method trusts. Works for any controller. | `Akeyless (Cert Auth)` |
| **API key** | Pre-shared `access_id` + `access_key`. Simple, no PKI, but the key is a long-lived bearer secret. | `Akeyless (API Key)` |
| **Kubernetes** | AWX runs in Kubernetes and an Akeyless customer gateway is reachable from the cluster. The pod's ServiceAccount JWT is the credential. | `Akeyless (Kubernetes Auth)` |

The rest of this document walks through CLI verification for each. After
verification, continue to [step 05](05-awx-credential-type.md) to register
the matching credential type in AWX.

## Endpoint terminology

Two distinct Akeyless endpoints exist, and they are not interchangeable.

| Endpoint | URL | Used by |
|---|---|---|
| Akeyless SaaS API | `https://api.akeyless.io` | All three auth methods. The handshake terminates here. |
| Customer gateway (self-hosted) | for example `https://your-gateway.example.com:8000/api/v1` | k8s auth only. The gateway is what calls Kubernetes TokenReview. Most customer-gateway ingresses do **not** forward TLS client certs through to the gateway pod, so cert auth fails there. |

The AWX cert-auth and API-key credential types default to the SaaS
endpoint. The k8s credential type adds a separate field for the gateway
URL.

## How the `akeyless` CLI picks an endpoint

Verified against CLI 1.139+. The URL is determined by env var and
profile, in this order:

1. `AKEYLESS_GATEWAY_URL` env var. If set, all calls route through it.
2. The active profile's `gateway_url` field, stored in
   `~/.akeyless/profiles/<profile>.toml`. Set or cleared via
   `akeyless configure --gateway-url <url>` (use `""` to clear).
3. Default: the Akeyless SaaS API.

For **cert** and **API-key** verification, both 1 and 2 must point at the
SaaS API. Empty (the CLI defaults to the SaaS API) or explicitly
`https://api.akeyless.io` both work; a customer gateway URL does not.

For **k8s** verification, set 1 or 2 to the customer gateway URL. K8s
auth is gateway-mediated.

### Inspect the active profile

```bash
cat ~/.akeyless/profiles/default.toml
```

Expected output (TOML with a `["default"]` section header; only the
`gateway_url` line matters):

```toml
["default"]
  default_location_prefix = ''
  gateway_url = ''
  cert_issuer_name = ''
  public_key_file_path = ''
  access_id = 'p-XXXXXXXXXXXXXX'
  access_type = 'access_key'
  cert_username = ''
  legacy_signing_alg = 'false'
  access_key = '...'
```

To clear the profile gateway:

```bash
akeyless configure --gateway-url ""
```

## Cert auth: verify with the CLI

From any machine that has the cert and key. The `env -u` clears any
inherited `AKEYLESS_GATEWAY_URL` so the CLI falls back to the profile or
SaaS default:

```bash
env -u AKEYLESS_GATEWAY_URL akeyless auth \
  --access-id p-XXXXXXXXXXXXXX \
  --access-type cert \
  --cert-file-name /path/to/client.crt \
  --key-file-name /path/to/client.key
```

Expected output:

```
Authentication succeeded.
Token: t-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Cert-auth failure modes

| Error | Diagnosis |
|---|---|
| `failed to read certificate: open <path>: no such file or directory` | The path is wrong or the file is unreadable. |
| `failed to get credentials: failed to parse private key` | The key PEM is malformed or encrypted. Re-export an unencrypted key. |
| `Unauthorized via gateway: https://...` | The CLI routed through a customer gateway whose ingress is not forwarding TLS client certs. Re-run with `env -u AKEYLESS_GATEWAY_URL` and clear the profile setting. |
| `unauthorized: certificate not allowed` or TLS handshake error from the SaaS | The cert was not issued by the CA the auth method trusts, or the cert has expired. |
| `unauthorized: missing role` | The auth method is not bound to a role that grants `read` on the path AWX will consume. |

## API-key auth: verify with the CLI

```bash
env -u AKEYLESS_GATEWAY_URL akeyless auth \
  --access-id p-XXXXXXXXXXXXXX \
  --access-type access_key \
  --access-key <ACCESS_KEY>
```

Expected output:

```
Authentication succeeded.
Token: t-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### API-key failure modes

| Error | Diagnosis |
|---|---|
| `unauthorized: invalid access key` | The access ID and access key do not match. Re-copy the access key from the Akeyless console. |
| `unauthorized: access denied` | The auth method is disabled or the source IP is outside the allowed CIDR. Check the auth method config. |
| `unauthorized: missing role` | The auth method has no role association, or the role does not grant the operation you need. |

> API keys are long-lived bearer secrets. Treat them like passwords:
> rotate on Akeyless when AWX is rebuilt or when the operator who created
> the credential leaves. Cert auth is preferable when you have CA
> infrastructure.

## Kubernetes auth: verify with the CLI

K8s auth assumes:

1. The customer has deployed an Akeyless gateway and given it
   permissions to call Kubernetes TokenReview against the cluster.
2. An Akeyless K8s auth method is configured, with the cluster
   registered as a K8s auth config.
3. A role is associated with the auth method and grants `read` on the
   intended secret path prefix.

Get a ServiceAccount JWT from a pod whose SA is bound to a role you
expect Akeyless to recognize:

```bash
kubectl exec -n <namespace> <pod-name> -- \
  cat /var/run/secrets/kubernetes.io/serviceaccount/token
```

Then run the handshake against the customer gateway. K8s auth requires
`AKEYLESS_GATEWAY_URL` to be set:

```bash
AKEYLESS_GATEWAY_URL=https://your-gateway.example.com:8000/api/v1 \
  akeyless auth \
    --access-id p-XXXXXXXXXXXXXX \
    --access-type k8s \
    --k8s-auth-config-name <CONFIG_NAME> \
    --k8s-service-account-token <JWT>
```

Expected output:

```
Authentication succeeded.
Token: t-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### K8s-auth failure modes

| Error | Diagnosis |
|---|---|
| `failed to validate token: connection refused` to the K8s API | The gateway cannot reach the cluster API. Check gateway egress and any authorized-networks rules on the cluster. |
| `failed to validate token: 403 Forbidden` from the K8s API | The token-reviewer JWT used by the gateway does not have permission to call TokenReview. Bind the `system:auth-delegator` ClusterRole to the gateway's SA. |
| `unauthorized: token signature invalid` | Wrong K8s auth config (the gateway is reviewing against a different cluster than the JWT belongs to), or the JWT is expired. |
| `unauthorized: bound service accounts mismatch` | The JWT belongs to an SA outside the auth method's `bound_sa_names` allowlist. Add the SA or use a different one. |
| `k8s auth name [...] not found` from the gateway | The k8s auth config has not been registered on the gateway. Run `akeyless gateway-create-k8s-auth-config` (see "Register the gateway k8s auth config" below). |
| `Cannot read Kubernetes ServiceAccount token from /var/run/secrets/...` from the inventory plugin | The AWX inventory-update pod does not have its SA token mounted. AWX-operator deployments often disable that mount. Either paste a JWT into the **ServiceAccount Token** field on the credential, or override the AWX execution pod spec to mount the SA token. |
| `400 Bad Request "access-id or email must be provided"` despite setting access_id | The k8s auth call hit the gateway's `/api/v1` legacy endpoint instead of `/api/v2`. The plugin auto-rewrites `/api/v1` to `/api/v2` when it sees `access_type=k8s`, so this only happens if the gateway URL has another path prefix or uses non-standard ports. Set the gateway URL to a form the plugin recognizes (`https://gw.example.com:8000`, `https://gw.example.com/api/v1`, or `https://gw.example.com/api/v2`). |

### Register the gateway k8s auth config

K8s auth requires both an Akeyless-side auth method **and** a corresponding
gateway-side config that knows how to call TokenReview against your cluster.
Without the gateway-side config, every authentication attempt fails with
`k8s auth name [...] not found`.

The minimal flow:

1. Create a token-reviewer ServiceAccount with `system:auth-delegator`:

   ```bash
   kubectl create namespace akeyless-gateway-auth
   kubectl -n akeyless-gateway-auth create serviceaccount akeyless-token-reviewer
   kubectl create clusterrolebinding akeyless-token-reviewer \
     --clusterrole=system:auth-delegator \
     --serviceaccount=akeyless-gateway-auth:akeyless-token-reviewer
   TR_TOKEN=$(kubectl -n akeyless-gateway-auth create token akeyless-token-reviewer --duration=87600h)
   ```

2. Capture the cluster API URL and CA cert in a form the gateway can use:

   ```bash
   APISERVER=https://kubernetes.default.svc.cluster.local
   kubectl config view --minify --raw \
     -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' \
     | base64 -d > /tmp/cluster-ca.pem
   CA_B64=$(base64 -w0 < /tmp/cluster-ca.pem)
   ```

3. Create the auth method on Akeyless and capture the returned `prv_key`:

   ```bash
   akeyless auth-method create k8s \
     --name /k8s-auth/awx \
     --json
   ```

   Save the returned `access_id` and `prv_key`. They cannot be retrieved
   later without regenerating the keypair.

4. Register the gateway k8s auth config using the prv_key as
   `--signing-key`:

   ```bash
   akeyless gateway-create-k8s-auth-config \
     --name awx \
     --gateway-url https://your-gateway.example.com \
     --access-id <access_id from step 3> \
     --signing-key <prv_key from step 3> \
     --k8s-host $APISERVER \
     --k8s-ca-cert $CA_B64 \
     --token-reviewer-jwt $TR_TOKEN
   ```

5. Bind the auth method to a role with `read,list` on the secret path
   AWX will consume.

After this setup, the CLI handshake above should succeed. Continue with
the rest of the verification.

## Verify the token can actually fetch a secret (any auth method)

A token-only success does not prove the role grants what AWX needs. List
one secret under your intended `secret_path_prefix`:

```bash
env -u AKEYLESS_GATEWAY_URL akeyless list-items \
  --path /apps/prod \
  --type static-secret \
  --token t-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Expected output:

```json
{
  "items": [
    { "item_name": "/apps/prod/db/password", "item_type": "STATIC_SECRET", ... },
    ...
  ]
}
```

If the items list is empty but you know secrets exist, the role bound to
the auth method does not grant `list` and `read` on `/apps/prod`. Fix the
role before continuing.

Resolve any failure here before continuing. Do not try to debug auth once
it is buried inside an AWX inventory sync log; the AWX surface only shows
a 401, not which of the above caused it.

## Next steps

- [AWX Custom Credential Type](05-awx-credential-type.md). Register the credential type and create a credential of that type using the verified credentials.
