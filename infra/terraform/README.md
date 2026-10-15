# Azure infrastructure

Everything the app needs on Azure, in one Terraform root:

| Resource | Why |
|---|---|
| PostgreSQL Flexible Server (B1ms, PG 17) + `azure.extensions = VECTOR` | documents, chunks, lessons, runs, evals |
| Container Apps environment (consumption) | `api` (internal ingress) and `web` (public), both scale to zero |
| Container Apps job `ingest` | downloads the book, checks its hash, loads it |
| Key Vault (RBAC) + user-assigned identity | the apps read the database URL and API keys at runtime |
| Storage account + Azure Files share | narration files, mounted at `/data/media` |
| Log Analytics workspace | container logs |
| Budget on the resource group | email at 50% spent and 90% forecast |

State lives in a Blob container created by `bootstrap/`, with Azure AD auth and blob-lease locking.

## First deploy

You need the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) and
[Terraform](https://developer.hashicorp.com/terraform/install) 1.9 or newer.

```
az login
cd infra/terraform/bootstrap
terraform init && terraform apply          # once: storage for the state
terraform output -raw backend_config > ../backend.hcl

cd ..
cp terraform.tfvars.example terraform.tfvars   # fill it in
terraform init -backend-config=backend.hcl
terraform plan -out tfplan
terraform apply tfplan
az containerapp job start -n "$(terraform output -raw ingest_job)" -g "$(terraform output -raw resource_group)"
```

The images come from GHCR, so the packages `microcourse-forge-api` and `microcourse-forge-web`
must be public (GitHub > Packages > settings), or the container apps can't pull them.

## Tear down

```
terraform destroy
```

The bootstrap storage stays; delete its resource group by hand if you are done for good.

## Things to know

- The database password and the storage key end up in the Terraform state. The state container is
  private, versioned and only reachable with Azure AD, which is why it isn't a local file.
- Postgres allows "Azure services" (`0.0.0.0`) instead of a private network. It is cheaper and
  simpler for a demo; a VNet with private endpoints is the step up.
- Without `anthropic_api_key` the deployed app serves the lessons already in the database and can't
  generate new ones (see `docs/adr/0002-llm-provider.md`).
- The API runs `alembic upgrade head` before starting. That is safe because it never runs more
  than one replica.
