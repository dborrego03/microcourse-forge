locals {
  name = "microcourse-${var.env}"
  tags = {
    project    = "microcourse-forge"
    env        = var.env
    managed_by = "terraform"
  }
  # Optional API keys only become secrets when they are set. Whether a key is set isn't
  # secret, so that can drive for_each; the values stay sensitive.
  api_key_values = {
    "anthropic-api-key" = var.anthropic_api_key
    "openai-api-key"    = var.openai_api_key
  }
  api_key_env = {
    for name, env in { "anthropic-api-key" = "ANTHROPIC_API_KEY", "openai-api-key" = "OPENAI_API_KEY" } :
    name => env if nonsensitive(local.api_key_values[name] != "")
  }
}

data "azurerm_client_config" "current" {}

# Storage accounts, key vaults and Postgres servers need globally unique names.
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

# --- Database: PostgreSQL Flexible Server with pgvector ---------------------------------

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-${local.name}-${random_string.suffix.result}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  version                       = "17"
  sku_name                      = "B_Standard_B1ms" # covered by the Azure free account for 12 months
  storage_mb                    = 32768
  backup_retention_days         = 7
  administrator_login           = "forge"
  administrator_password        = random_password.db.result
  public_network_access_enabled = true
  tags                          = local.tags

  lifecycle {
    # Azure picks the zone; don't fight it on later plans.
    ignore_changes = [zone]
  }
}

# pgvector has to be allow-listed before CREATE EXTENSION works.
resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "VECTOR"
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = "microcourse"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# 0.0.0.0 is Azure's convention for "allow other Azure services", which is how the
# container apps reach the server without a private network (cheaper, simpler).
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# --- Secrets: Key Vault, read by the apps through a managed identity --------------------

resource "azurerm_user_assigned_identity" "apps" {
  name                = "id-${local.name}-apps"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags
}

resource "azurerm_key_vault" "main" {
  name                       = "kv-mcf-${var.env}-${random_string.suffix.result}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  tags                       = local.tags
}

resource "azurerm_role_assignment" "deployer_writes_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "apps_read_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  key_vault_id = azurerm_key_vault.main.id
  value = format(
    "postgresql://forge:%s@%s:5432/%s?sslmode=require",
    random_password.db.result,
    azurerm_postgresql_flexible_server.main.fqdn,
    azurerm_postgresql_flexible_server_database.main.name,
  )
  depends_on = [azurerm_role_assignment.deployer_writes_secrets]
}

resource "azurerm_key_vault_secret" "api_keys" {
  for_each     = local.api_key_env
  name         = each.key
  key_vault_id = azurerm_key_vault.main.id
  value        = local.api_key_values[each.key]
  depends_on   = [azurerm_role_assignment.deployer_writes_secrets]
}

# --- Narration files: an Azure Files share mounted at /data/media ------------------------

resource "azurerm_storage_account" "media" {
  name                            = "stmcf${var.env}${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_storage_share" "media" {
  name               = "media"
  storage_account_id = azurerm_storage_account.media.id
  quota              = 5
}

# --- Container Apps (consumption plan, scale to zero) -----------------------------------

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.name}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

resource "azurerm_container_app_environment_storage" "media" {
  name                         = "media"
  container_app_environment_id = azurerm_container_app_environment.main.id
  account_name                 = azurerm_storage_account.media.name
  share_name                   = azurerm_storage_share.media.name
  access_key                   = azurerm_storage_account.media.primary_access_key
  access_mode                  = "ReadWrite"
}

resource "azurerm_container_app" "api" {
  name                         = "ca-${local.name}-api"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.apps.id]
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
    identity            = azurerm_user_assigned_identity.apps.id
  }

  dynamic "secret" {
    for_each = azurerm_key_vault_secret.api_keys
    content {
      name                = secret.key
      key_vault_secret_id = secret.value.versionless_id
      identity            = azurerm_user_assigned_identity.apps.id
    }
  }

  template {
    min_replicas = 0
    max_replicas = 1

    container {
      name   = "api"
      image  = var.api_image
      cpu    = 1.0
      memory = "2Gi"
      # One replica at most, so running migrations on start is safe and saves a job.
      command = ["sh", "-c", "alembic upgrade head && uvicorn forge.api:app --host 0.0.0.0 --port 8000"]

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      dynamic "env" {
        for_each = local.api_key_env
        content {
          name        = env.value
          secret_name = env.key
        }
      }

      volume_mounts {
        name = "media"
        path = "/data/media"
      }

      readiness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/health"
      }
    }

    volume {
      name         = "media"
      storage_type = "AzureFile"
      storage_name = azurerm_container_app_environment_storage.media.name
    }
  }

  # Only the web app can reach the API.
  ingress {
    external_enabled = false
    target_port      = 8000
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  depends_on = [azurerm_role_assignment.apps_read_secrets]
}

resource "azurerm_container_app" "web" {
  name                         = "ca-${local.name}-web"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags                         = local.tags

  template {
    min_replicas = 0
    max_replicas = 1

    container {
      name   = "web"
      image  = var.web_image
      cpu    = 0.5
      memory = "1Gi"
      env {
        name  = "API_URL"
        value = "https://${azurerm_container_app.api.ingress[0].fqdn}"
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 3000
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

# Loads the book into the database. Start it by hand (or from CI) after the first deploy:
#   az containerapp job start -n <name> -g <resource group>
resource "azurerm_container_app_job" "ingest" {
  name                         = "caj-${local.name}-ingest"
  resource_group_name          = azurerm_resource_group.main.name
  location                     = azurerm_resource_group.main.location
  container_app_environment_id = azurerm_container_app_environment.main.id
  replica_timeout_in_seconds   = 1800
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.apps.id]
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
    identity            = azurerm_user_assigned_identity.apps.id
  }

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name    = "ingest"
      image   = var.api_image
      cpu     = 1.0
      memory  = "2Gi"
      command = ["sh", "-c", "alembic upgrade head && python -m forge.ingest --url \"$CORPUS_URL\""]
      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name  = "CORPUS_URL"
        value = var.corpus_url
      }
    }
  }

  depends_on = [azurerm_role_assignment.apps_read_secrets]
}

# --- Cost guard ------------------------------------------------------------------------

resource "azurerm_consumption_budget_resource_group" "main" {
  name              = "budget-${local.name}"
  resource_group_id = azurerm_resource_group.main.id
  amount            = var.monthly_budget
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.alert_email]
  }

  notification {
    enabled        = true
    threshold      = 90
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = [var.alert_email]
  }
}
