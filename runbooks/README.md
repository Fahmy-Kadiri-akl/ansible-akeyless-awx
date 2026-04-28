# Runbooks

Step-by-step operator guides for wiring `akeyless.awx_integration` into an
existing AWX/AAP install.

## Reading order

The runbooks are numbered and depend on each other in order. First-time
setup runs straight through 01 -> 09. Day-2 operators usually only need 08
and 09.

| # | Document | When you need it |
|---|---|---|
| 1 | [Architecture overview](01-architecture-overview.md) | Read once before starting, so the rest of the steps make sense. |
| 2 | [Prerequisites](02-prerequisites.md) | Verify before starting. Most failures later trace back to a missed prereq. |
| 3 | [Execution Environment](03-execution-environment.md) | Pick or build the EE that runs the inventory plugin. |
| 4 | [Akeyless cert-auth verification](04-akeyless-cert-auth.md) | Confirm cert auth works against the SaaS API **before** touching AWX. |
| 5 | [AWX Custom Credential Type](05-awx-credential-type.md) | Register the credential type and create a credential of that type. |
| 6 | [Inventory source configuration](06-inventory-source.md) | Wire the project, inventory, credential, and EE into an inventory source. |
| 7 | [First sync and test job](07-first-sync-and-job.md) | Run the inventory sync, verify host_vars, run a playbook end to end. |
| 8 | [Day-2 operations](08-day-2-operations.md) | Rotation, adding/removing secrets, revocation, EE refresh, multi-environment. |
| 9 | [Troubleshooting](09-troubleshooting.md) | Categorized failure modes with diagnoses and fixes. |

The repository-level [`../README.md`](../README.md) covers what the
collection is, why it exists, and how it relates to the official
`akeyless.secrets_management` collection.
