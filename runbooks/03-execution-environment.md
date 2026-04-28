# Execution Environment

The Execution Environment (EE) is the container image AWX runs every
inventory sync inside. It must contain three things this collection needs:

1. The `akeyless` Python SDK (>= 5.0, < 6.0).
2. The official `akeyless.secrets_management` collection.
3. This collection (`akeyless.awx_integration`).

The default `quay.io/ansible/awx-ee:latest` image contains none of the
above, and AWX does not install project-level `requirements.txt` for
inventory updates. You must either use the published reference EE or build
your own.

## Option A (recommended): use the published reference EE

A pre-built EE is published on GHCR.

```
ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:0.1.0
```

- Built on `quay.io/ansible/awx-ee:latest`.
- Adds `akeyless.secrets_management`, `akeyless.awx_integration`, and the
  `akeyless` Python SDK.
- Public. Pulls require no authentication.
- Rebuilt every Monday at 09:00 UTC by `.github/workflows/ee-build.yml`.
- Scanned daily by `.github/workflows/ee-scan.yml` (Trivy SARIF in the
  Security tab).

### Verify the image is reachable

```bash
docker pull ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:0.1.0
```

Expected output:

```
0.1.0: Pulling from fahmy-kadiri-akl/akeyless-awx-ee
...
Status: Downloaded newer image for ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:0.1.0
```

### Available tags

| Tag | When to use |
|---|---|
| `0.1.0` | Pin to a specific collection version. Use this in production for reproducibility. |
| `latest` | Tracks the most recent successful build. Convenient for first-time tests. Do not pin to it in prod, because it moves. |
| `weekly-YYYY-MM-DD` | Each weekly rebuild also gets a date-stamped tag. Use this if you want a dated, immutable pin. |

## Option B: build your own EE

For private registries, custom bases, internal supply-chain controls, or
air-gapped environments, the `ee/` directory is a working `ansible-builder`
v3 context.

### Files in `ee/`

| File | Role |
|---|---|
| `execution-environment.yml` | EE definition: base image, Galaxy collections, Python deps, build steps. |
| `requirements.txt` | Python deps (currently `akeyless>=5.0,<6.0`). |

### Build the collection tarball first

The `append_galaxy` step in `execution-environment.yml` installs this
collection from a tarball at `ee/akeyless-awx_integration.tar.gz`. Build
the tarball before running `ansible-builder`:

```bash
ansible-galaxy collection build --output-path . .
mv akeyless-awx_integration-*.tar.gz ee/akeyless-awx_integration.tar.gz
```

### Build the EE image

```bash
cd ee
ansible-builder build \
  -t your-registry.example/akeyless-awx-ee:0.1.0 \
  -f execution-environment.yml \
  --container-runtime docker
```

Expected output (last lines):

```
...
Complete! The build context can be found at: /path/to/ee/context
Successfully built your-registry.example/akeyless-awx-ee:0.1.0
```

### Push to your registry

```bash
docker push your-registry.example/akeyless-awx-ee:0.1.0
```

If your base image must come from an internal registry, edit
`ee/execution-environment.yml`'s `images.base_image.name`. Keep it on an
`awx-ee`-derived base. The EE makes assumptions about Python 3.12 and the
`awx-ee` filesystem layout.

## Register the EE in AWX

Navigate: **Administration -> Execution Environments -> Add**.

| Field | Value |
|---|---|
| **Name** | `akeyless-awx-ee` (or any label you prefer). |
| **Image** | The full image ref. Option A: `ghcr.io/fahmy-kadiri-akl/akeyless-awx-ee:0.1.0`. Option B: what you pushed in the build step. |
| **Pull policy** | `always` for production, so weekly rebuilds are picked up automatically. `missing` for first-time tests. |
| **Credential** | None for the public GHCR image. A registry credential if option B with a private registry. |

Click **Save**.

### Verify

The EE appears in **Administration -> Execution Environments** and is
selectable from the EE dropdown when you create an inventory source in
[step 06](06-inventory-source.md).

## Next steps

- [Akeyless cert-auth verification](04-akeyless-cert-auth.md). Confirm cert auth works against the SaaS API before touching any AWX object that depends on it.
