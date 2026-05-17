
output "database_public_ip" {
  value = azurerm_public_ip.database_pip.ip_address
}

output "webserver_public_ip" {
  value = azurerm_public_ip.webserver_pip.ip_address
}

output "mongo_connection_string" {
  value = "mongodb://${azurerm_public_ip.database_pip.ip_address}:27017"
}

output "webserver_port_3000_url" {
  value = "http://${azurerm_public_ip.webserver_pip.ip_address}:3000"
}

output "webserver_port_8001_url" {
  value = "http://${azurerm_public_ip.webserver_pip.ip_address}:8001"
}
