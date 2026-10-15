# Run once, with local state, to create the storage that holds the real state.
#   cd infra/terraform/bootstrap && terraform init && terraform apply
# Then copy the outputs into ../backend.hcl.

terraform {
  required_version = ">= 1.9"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 5.10" }
    random  = { source = "hashicorp/random", version = "~> 3.9" }
  }
}

provider "azurerm" {
  features {}
}

variable "location" {
  type    = string
  default = "westeurope"
}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_resource_group" "state" {
  name     = "rg-microcourse-tfstate"
  location = var.location
  tags     = { project = "microcourse-forge", managed_by = "terraform" }
}

resource "azurerm_storage_account" "state" {
  name                            = "stmcftfstate${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.state.name
  location                        = azurerm_resource_group.state.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  # The state holds secrets (database password, storage key), so keep old versions
  # recoverable and never expose the container publicly.
  blob_properties {
    versioning_enabled = true
  }
  tags = azurerm_resource_group.state.tags
}

resource "azurerm_storage_container" "state" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
}

output "backend_config" {
  value = <<-EOT
    resource_group_name  = "${azurerm_resource_group.state.name}"
    storage_account_name = "${azurerm_storage_account.state.name}"
    container_name       = "${azurerm_storage_container.state.name}"
    key                  = "microcourse-forge.tfstate"
    use_azuread_auth     = true
  EOT
}
