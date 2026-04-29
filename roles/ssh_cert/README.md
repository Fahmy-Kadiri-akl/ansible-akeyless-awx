# Role: `akeyless.awx_integration.ssh_cert`

Materializes the Akeyless-signed SSH certificate and matching private key
that the `akeyless.awx_integration.akeyless` inventory plugin attaches as
host_vars, then wires the SSH connection to use them.

Import at the top of any play that targets hosts whose inventory was
synced with `ssh_cert_issuer` set on the inventory source.

## Usage

```yaml
- name: Run something on the prod_apps group
  hosts: prod_apps
  gather_facts: false
  tasks:
    - name: Wire the Akeyless-signed SSH cert into this play
      ansible.builtin.import_role:
        name: akeyless.awx_integration.ssh_cert

    # All subsequent tasks run as the cert subject, authenticated by
    # the Akeyless-signed certificate. No `password` or
    # `--private-key` flag needed.
    - name: Whoami
      ansible.builtin.command: whoami
      register: who
    - ansible.builtin.debug: var=who.stdout
```

## What it expects

The inventory plugin attaches three host_vars when `ssh_cert_issuer` is
configured:

| host_var | Source | Used for |
|---|---|---|
| `akeyless_ssh_signed_cert` | `akeyless get-ssh-certificate` response | Written to the cert file passed via `-o CertificateFile=...` |
| `akeyless_ssh_private_key` | The Akeyless static secret named in `ssh_cert_private_key_secret` | Written to the file passed via `ansible_ssh_private_key_file` |
| `akeyless_ssh_cert_username` | The plugin's `ssh_cert_username` option | Set as `ansible_user` |

If any of those is missing, the role fails with a clear message; the
likely cause is that the inventory was synced without
`ssh_cert_issuer` set.

## What it sets

| fact | Value |
|---|---|
| `ansible_user` | from `akeyless_ssh_cert_username` |
| `ansible_ssh_private_key_file` | path to the freshly-written key file |
| `ansible_ssh_extra_args` | `-o CertificateFile=<cert-path> -o IdentitiesOnly=yes` |

The two files live under `akeyless_ssh_cert_files_dir` (default
`/tmp/akeyless-ssh`), one pair per `inventory_hostname`. Inside the AWX
EE pod, that directory is wiped when the pod terminates at the end of
the job, so secret material does not persist.

## Variables you may override

| Variable | Default | Purpose |
|---|---|---|
| `akeyless_ssh_cert_files_dir` | `/tmp/akeyless-ssh` | Where the role writes the key and cert. |
| `akeyless_ssh_cert_overwrite` | `true` | Whether to overwrite existing files; default `true` so each play picks up the freshest cert from the inventory. |
