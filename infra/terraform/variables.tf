variable "env" {
  description = "Environment name, used in resource names and tags."
  type        = string
  default     = "dev"
}

variable "location" {
  type    = string
  default = "westeurope"
}

variable "api_image" {
  description = "API image, e.g. ghcr.io/dborrego03/microcourse-forge-api:<sha>"
  type        = string
}

variable "web_image" {
  description = "Web image, e.g. ghcr.io/dborrego03/microcourse-forge-web:<sha>"
  type        = string
}

variable "anthropic_api_key" {
  description = "Optional. Without it the deployed app serves existing lessons but can't generate new ones."
  type        = string
  default     = ""
  sensitive   = true
}

variable "openai_api_key" {
  description = "Optional. Turns on narration."
  type        = string
  default     = ""
  sensitive   = true
}

variable "corpus_url" {
  description = "Where the ingestion job downloads the book (its SHA-256 is checked in code)."
  type        = string
  default     = "https://assets.openstax.org/oscms-prodcms/media/documents/Psychology2e_WEB.pdf"
}

variable "monthly_budget" {
  description = "Monthly budget for the resource group, in the subscription's currency."
  type        = number
  default     = 20
}

variable "budget_start_date" {
  description = "First day of the month the budget starts, e.g. 2026-11-01T00:00:00Z."
  type        = string
}

variable "alert_email" {
  description = "Where budget alerts go."
  type        = string
}
