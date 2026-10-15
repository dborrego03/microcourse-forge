output "web_url" {
  value = "https://${azurerm_container_app.web.ingress[0].fqdn}"
}

output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "ingest_job" {
  value = azurerm_container_app_job.ingest.name
}

output "postgres_fqdn" {
  value = azurerm_postgresql_flexible_server.main.fqdn
}
