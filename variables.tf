
variable "resource_group_name" {
  type    = string
  default = "rg-school-2vm"
}

variable "location" {
  type    = string
  default = "Central India"
}

variable "admin_username" {
  type    = string
  default = "azureuser"
}

variable "admin_password" {
  type      = string
  sensitive = true
  default   = "Manasa@123"
}

variable "allowed_source_cidr" {
  type        = string
  default     = "*"
  description = "Use your public IP in CIDR form for better security, for example 203.0.113.10/32"
}
