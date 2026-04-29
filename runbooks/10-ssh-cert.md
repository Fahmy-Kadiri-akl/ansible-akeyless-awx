# Just-in-time SSH Certificates via Akeyless

This runbook covers the SSH-cert flow specifically. The plugin signs
an SSH public key against an Akeyless SSH certificate issuer on each
inventory sync, attaches the signed cert + matching private key as
host_vars, and a small Ansible role wires the SSH connection to use
them. Playbooks contain no Akeyless code.

This is the alternative to baking long-lived SSH keys into AWX
credentials: every job picks up a freshly-signed short-lived cert.

## Prerequisites

In addition to the base prereqs from
[step 02](02-prerequisites.md):

| Need | How to check |
|---|---|
| An Akeyless SSH cert issuer | `akeyless list-items --type ssh-cert-issuer --token <admin-token>`. The issuer's `cert_issue_details.ssh_cert_issuer_details.allowed_users` defines who you can sign for. |
| The username you intend to use is in the issuer's `allowed_users` | `akeyless describe-item --name <issuer-name> --json` and check `certificate_issue_details.ssh_cert_issuer_details.allowed_users`. |
| The SSH keypair that will be used by AWX | An OpenSSH-format private key. The matching public key will be signed; the private key must live in an Akeyless static secret. See "Seed the keypair" below. |
| The role bound to your AWX cert auth method has `read+list` on the SSH issuer's path | `akeyless set-role-rule --role-name <role> --path "/path/to/ssh-issuers/*" --capability read --capability list --token <admin-token>` if not already granted. |
| The target SSH server trusts the issuer's CA | The target's `sshd_config` references a `TrustedUserCAKeys` file containing the issuer's public CA. The issuer's CA can be retrieved with `akeyless get-ssh-certificate-issuer-public-key --name <issuer>`. Out of scope for this runbook; consult your platform team. |

## Step 1: seed the SSH keypair as an Akeyless static secret

Generate a fresh keypair on a machine that won't keep the private key
around:

```bash
ssh-keygen -t rsa -b 2048 -f /tmp/awx-ssh -N '' -C 'awx'
```

You now have:

- `/tmp/awx-ssh` (private key, OpenSSH format, ~1800 bytes)
- `/tmp/awx-ssh.pub` (public key, single line starting `ssh-rsa AAAA...`)

Upload the private key to Akeyless. The CLI's `--value` flag does not
handle multi-line PEMs, so use the SDK directly:

```bash
ADMIN_TOKEN=$(akeyless auth --access-id <admin-id> --access-type access_key --access-key <admin-key> --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

docker run --rm -v /tmp/awx-ssh:/key:ro <your-EE-image> python3 -c "
import akeyless
cfg = akeyless.Configuration(host='https://api.akeyless.io')
api = akeyless.V2Api(akeyless.ApiClient(cfg))
priv = open('/key').read()
body = akeyless.CreateSecret(
  name='/apps/prod/ssh_private_key',
  value=priv,
  token='${ADMIN_TOKEN}'
)
resp = api.create_secret(body)
print('created, item_id:', getattr(resp, 'item_id', None))"
```

Verify the readback length matches the file:

```bash
akeyless get-secret-value --name /apps/prod/ssh_private_key --token <token> | wc -c
# 1824 for a 2048-bit RSA OpenSSH private key (1823 bytes + trailing newline)
```

## Step 2: confirm the cert auth role can call the issuer

Sign a throwaway public key as a smoke test:

```bash
TOK=$(akeyless auth --access-id <awx-cert-auth-access-id> \
  --access-type cert \
  --cert-file-name /path/to/client.crt \
  --key-file-name /path/to/client.key \
  --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

akeyless get-ssh-certificate \
  --cert-issuer-name /5-SSH-CERT-ISSUER/SSH/your-issuer \
  --cert-username ubuntu \
  --public-key-data "$(cat /tmp/awx-ssh.pub)" \
  --token "$TOK"
```

Expected output:

```
SSH certificate file successfully created:
rsa-sha2-256-cert-v01@openssh.com AAAAHHNzaC1yc2EtY2VydC12MDFAb3BlbnNzaC5jb20...
```

A line that begins with `rsa-sha2-256-cert-v01@openssh.com` (or
`ecdsa-sha2-...-cert-v01@openssh.com`, depending on your issuer's
`cert_type`) confirms:

- The role bound to your cert auth method has read on the issuer.
- The username `ubuntu` is in the issuer's `allowed_users`.
- The cert auth itself works (covered in [step 04](04-akeyless-cert-auth.md)).

If you see `not part of allowed user list`, fix the username to one
the issuer accepts.

If you see `failed to obtain item ...`, the role does not have read
on the issuer's path. Add the rule:

```bash
akeyless set-role-rule \
  --role-name <your-role> \
  --path "/5-SSH-CERT-ISSUER/SSH/*" \
  --capability read --capability list \
  --token "$ADMIN_TOKEN"
```

## Step 3: configure the inventory source

Commit a YAML like this to your AWX project. Filename must end with
`akeyless.yml` or `akeyless.yaml` (the plugin's `verify_file()`
silently skips other names):

```yaml
# examples/ssh-cert.akeyless.yml
plugin: akeyless.awx_integration.akeyless

hosts:
  - app01.example.com
  - app02.example.com
default_group: ssh_cert_demo

ssh_cert_issuer: /5-SSH-CERT-ISSUER/SSH/your-issuer
ssh_cert_username: ubuntu
ssh_cert_private_key_secret: /apps/prod/ssh_private_key
ssh_cert_public_key: ssh-rsa AAAA...your-public-key... awx
```

A ready-to-use copy is committed in this repo at
`examples/ssh-cert.akeyless.yml`. Replace the issuer name, username,
secret path, and public key with your tenant's values.

Then create the AWX inventory + inventory source as in
[step 06](06-inventory-source.md), pointing at this YAML.

### Trigger the sync and confirm host_vars

```bash
AWX=https://<awx-host>
AUTH=admin:<password>

NEW=$(curl -sk -u "$AUTH" -X POST "$AWX/api/v2/inventory_sources/$SRC_ID/update/" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("inventory_update"))')
echo "INV_UPDATE=$NEW"
```

Wait for `status=successful`, then inspect a host:

```bash
HOST_ID=$(curl -sk -u "$AUTH" "$AWX/api/v2/inventories/$INV_ID/hosts/?name=app01.example.com" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["results"][0]["id"])')

curl -sk -u "$AUTH" "$AWX/api/v2/hosts/$HOST_ID/variable_data/" \
  | python3 -c '
import json, sys
v = json.load(sys.stdin)
print("var count:", len(v))
for k in sorted(v):
    s = str(v[k])
    print(f"  {k} ({len(s)} chars)")'
```

Expected output:

```
var count: 3
  akeyless_ssh_cert_username (6 chars)
  akeyless_ssh_private_key (1824 chars)
  akeyless_ssh_signed_cert (1547 chars)
```

The signed cert size varies by issuer (RSA vs ECDSA, principal count,
TTL). What matters is that all three host_vars are present and
non-empty.

## Step 4: import the role in your playbook

The role does the wiring. Without it, the SSH client in the EE has no
way to find the cert + key files.

```yaml
- name: Run things on the ssh_cert_demo group
  hosts: ssh_cert_demo
  gather_facts: false
  tasks:
    - name: Wire the Akeyless-signed SSH cert into this play
      ansible.builtin.import_role:
        name: akeyless.awx_integration.ssh_cert

    # Subsequent tasks SSH to the target as ubuntu, authenticated by
    # the Akeyless-signed cert. No password, no -i flag.
    - name: Whoami
      ansible.builtin.command: whoami
      register: who
    - ansible.builtin.debug: var=who.stdout
```

A reference smoke playbook is at `examples/ssh_cert_smoke.yml`. It
imports the role, asserts the connection facts are set, asserts the
materialized files exist on the controller, and prints their sizes
(never the contents). It uses `connection: local` because the example
hosts are fictional placeholders.

## Step 5: confirm against the smoke playbook

Create a job template pointing at `examples/ssh_cert_smoke.yml` and
launch it. Expected output (full play recap):

```
TASK [Assert connection facts are set by the role] *****************************
ok: [app01.example.com] => {"msg": "All assertions passed"}
ok: [app02.example.com] => {"msg": "All assertions passed"}

TASK [Assert files were written by the role] ***********************************
ok: [app01.example.com] => {"msg": "All assertions passed"}
ok: [app02.example.com] => {"msg": "All assertions passed"}

TASK [Show file sizes (no contents)] *******************************************
ok: [app01.example.com] => {"msg": "app01.example.com key=1823b cert=1547b user=ubuntu"}
ok: [app02.example.com] => {"msg": "app02.example.com key=1823b cert=1547b user=ubuntu"}

PLAY RECAP *********************************************************************
app01.example.com          : ok=10   changed=0    unreachable=0    failed=0
app02.example.com          : ok=9    changed=0    unreachable=0    failed=0
```

`ok=10` (or `9`) on both hosts with no failures means:

- The plugin signed the cert and attached host_vars correctly.
- The role read those host_vars and wrote the cert + key files.
- The role set `ansible_user`, `ansible_ssh_private_key_file`, and
  `ansible_ssh_extra_args`.

## Step 6: real SSH against a target

The smoke playbook only verifies the wiring, not that an actual SSH
session opens. To test against a real host:

1. Drop `connection: local` from your playbook.
2. Confirm the target's `sshd_config` has:
   ```
   TrustedUserCAKeys /etc/ssh/akeyless-issuer-ca.pub
   ```
   where the file holds the issuer's CA public key (retrieve once with
   `akeyless get-ssh-certificate-issuer-public-key --name <issuer>` or
   the equivalent UI).
3. Confirm the target has an `AuthorizedPrincipalsFile` or a matching
   user account for the cert's username (`ubuntu` in the example).
4. Re-launch the job. The first task that exercises the SSH connection
   (e.g. `ansible.builtin.command: whoami`) should succeed without
   prompting for a password or accepting an unknown host key.

## Day-2

- **Cert TTL**: the issuer's `max_ttl` controls how long each signed
  cert is valid. With `update_on_launch: true` on the inventory source,
  every job mints a fresh cert seconds before the play, so a 5-minute
  TTL is usually fine. Long-running plays must finish before the cert
  expires.
- **Rotating the SSH keypair**: generate a new keypair, upload the
  private key to the same Akeyless static secret with `update-secret-val`
  via the SDK (same multi-line workaround), update `ssh_cert_public_key`
  in the inventory YAML, push. Next sync uses the new keypair.
- **Restricting principals**: tighten `ssh_cert_username` (it becomes
  the cert's principal) or pre-populate `ssh_cert_principals` with the
  exact set of usernames you want the cert to be valid for.

## Next steps

- [Day-2 operations](08-day-2-operations.md) for rotation, EE refresh,
  multi-environment patterns.
