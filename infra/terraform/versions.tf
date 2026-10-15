terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 5.10" }
    random  = { source = "hashicorp/random", version = "~> 3.9" }
  }

  # Remote state in Blob storage (created by bootstrap/), with blob-lease locking.
  # terraform init -backend-config=backend.hcl
  backend "azurerm" {}
}

provider "azurerm" {
  features {
    key_vault {
      # Lets `terraform destroy` followed by `apply` reuse the vault name.
      purge_soft_delete_on_destroy = true
    }
  }
}
