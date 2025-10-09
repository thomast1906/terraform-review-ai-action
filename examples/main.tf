# Azure Provider configuration
terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

# Data source for current client config
data "azurerm_client_config" "current" {}

# Resource Group
resource "azurerm_resource_group" "main" {
  name     = "rg-azure-test-prod"
  location = "East US"

  tags = {
    Environment = "Production"
    Project     = "Azure-Test"
    Owner       = "DevOps-Team"
  }
}

# Virtual Network
resource "azurerm_virtual_network" "main" {
  name                = "vnet-azure-test"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  tags = {
    Environment = "Production"
  }
}

# Subnets
resource "azurerm_subnet" "web" {
  name                 = "subnet-web"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.1.0/24"]
}

resource "azurerm_subnet" "database" {
  name                 = "subnet-database"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.2.0/24"]
}

# Network Security Group
resource "azurerm_network_security_group" "web" {
  name                = "nsg-web"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  security_rule {
    name                       = "HTTP"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "HTTPS"
    priority                   = 1002
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = {
    Environment = "Production"
  }
}

# Storage Account
resource "azurerm_storage_account" "main" {
  name                     = "stazuretestprod001"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  
  https_traffic_only_enabled = true
  min_tls_version            = "TLS1_2"

  tags = {
    Environment = "Production"
  }
}

# Storage Container
resource "azurerm_storage_container" "uploads" {
  name                  = "uploads"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# Key Vault
resource "azurerm_key_vault" "main" {
  name                        = "kv-azure-test-prod"
  location                    = azurerm_resource_group.main.location
  resource_group_name         = azurerm_resource_group.main.name
  enabled_for_disk_encryption = true
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  soft_delete_retention_days  = 7
  purge_protection_enabled    = false

  sku_name = "standard"

  tags = {
    Environment = "Production"
  }
}

# PostgreSQL Server
resource "azurerm_postgresql_server" "main" {
  name                = "psql-azure-test-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  administrator_login          = "psqladmin"
  administrator_login_password = "H@Sh1CoR3!"

  sku_name   = "GP_Gen5_2"
  version    = "11"
  storage_mb = 5120

  backup_retention_days        = 7
  geo_redundant_backup_enabled = false
  auto_grow_enabled            = true

  ssl_enforcement_enabled          = true
  ssl_minimal_tls_version_enforced = "TLS1_2"

  tags = {
    Environment = "Production"
  }
}

# PostgreSQL Database
resource "azurerm_postgresql_database" "main" {
  name                = "maindb"
  resource_group_name = azurerm_resource_group.main.name
  server_name         = azurerm_postgresql_server.main.name
  charset             = "UTF8"
  collation           = "English_United States.1252"
}

# App Service Plan
resource "azurerm_app_service_plan" "main" {
  name                = "asp-azure-test-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  kind                = "Linux"
  reserved            = true

  sku {
    tier = "Standard"
    size = "S1"
  }

  tags = {
    Environment = "Production"
  }
}

# App Service
resource "azurerm_app_service" "main" {
  name                = "app-azure-test-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  app_service_plan_id = azurerm_app_service_plan.main.id
  https_only          = true

  site_config {
    linux_fx_version = "NODE|14-lts"
    always_on        = true
    ftps_state       = "Disabled"
  }

  app_settings = {
    "WEBSITE_NODE_DEFAULT_VERSION" = "14.17.0"
  }

  tags = {
    Environment = "Production"
  }
}

# Application Insights
resource "azurerm_application_insights" "main" {
  name                = "appi-azure-test-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  application_type    = "web"

  tags = {
    Environment = "Production"
  }
}

# Log Analytics Workspace
resource "azurerm_log_analytics_workspace" "main" {
  name                = "law-azure-test-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30

  tags = {
    Environment = "Production"
  }
}

# Container Registry
resource "azurerm_container_registry" "main" {
  name                = "acrazuretestprod"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Standard"
  admin_enabled       = false

  tags = {
    Environment = "Production"
  }
}

# AKS Cluster
resource "azurerm_kubernetes_cluster" "main" {
  name                = "aks-azure-test-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "aksazuretest"
  kubernetes_version  = "1.25.6"

  default_node_pool {
    name           = "default"
    node_count     = 2
    vm_size        = "Standard_D2_v2"
    vnet_subnet_id = azurerm_subnet.web.id
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin = "azure"
    service_cidr   = "10.1.0.0/16"
    dns_service_ip = "10.1.0.10"
  }

  tags = {
    Environment = "Production"
  }
}

# Public IP for Load Balancer
resource "azurerm_public_ip" "lb" {
  name                = "pip-lb-azure-test"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    Environment = "Production"
  }
}

# Load Balancer
resource "azurerm_lb" "main" {
  name                = "lb-azure-test-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Standard"

  frontend_ip_configuration {
    name                 = "PublicIPAddress"
    public_ip_address_id = azurerm_public_ip.lb.id
  }

  tags = {
    Environment = "Production"
  }
}

# Redis Cache
resource "azurerm_redis_cache" "main" {
  name                = "redis-azure-test-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  capacity            = 1
  family              = "C"
  sku_name            = "Standard"
  non_ssl_port_enabled = false
  minimum_tls_version  = "1.2"

  redis_configuration {
    maxmemory_reserved = 10
    maxmemory_delta    = 10
    maxmemory_policy   = "allkeys-lru"
  }

  tags = {
    Environment = "Production"
  }
}

# Monitor Action Group
resource "azurerm_monitor_action_group" "main" {
  name                = "ag-azure-test-prod"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "aztest"

  email_receiver {
    name          = "devops-team"
    email_address = "devops@company.com"
  }

  tags = {
    Environment = "Production"
  }
}

# Cosmos DB
resource "azurerm_cosmosdb_account" "main" {
  name                = "cosmos-azure-test-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.main.location
    failover_priority = 0
  }

  tags = {
    Environment = "Production"
  }
}
