#!/usr/bin/env python3
"""
Terraform AI Plan Analyser
A provider-agnostic Terraform plan analysis tool using OpenAI and HashiCorp MCP Server
"""

import json
import os
import re
import sys
import glob
import uuid
import asyncio
import subprocess
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class AnalysisConfig:
    """Configuration for the analysis"""
    ai_provider: str = "azure"  # "azure" (OpenAI-compatible models) or "azure-anthropic" (Claude models), both on Microsoft Foundry
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_deployment: str = "gpt-5-mini"
    terraform_plan_path: str = "tfplan.json"
    terraform_directory: str = "."
    analysis_focus: List[str] = None
    analysis_mode: str = "comprehensive"  # "plan-only" or "comprehensive"
    analysis_style: str = "severity"  # "severity" or "domain"
    analysis_depth: str = "standard"  # "quick", "standard", or "detailed"
    mcp_available: bool = False
    skip_mcp: bool = False
    show_mcp_details: bool = False  # Show detailed MCP analysis section for troubleshooting

    def __post_init__(self):
        if self.analysis_focus is None:
            self.analysis_focus = ['security', 'cost', 'best-practices', 'deployment']


class CloudProviderDetector:
    """Detects cloud provider from Terraform configuration"""
    
    PROVIDER_PATTERNS = {
        'aws': ['aws_', 'amazon-', 'aws.', 'provider "aws"'],
        'azure': ['azurerm_', 'azure_', 'azuread_', 'provider "azurerm"', 'provider "azure"'],
        'gcp': ['google_', 'gcp_', 'provider "google"', 'provider "google-beta"'],
        'kubernetes': ['kubernetes_', 'helm_', 'provider "kubernetes"', 'provider "helm"'],
        'cloudflare': ['cloudflare_', 'provider "cloudflare"'],
        'digitalocean': ['digitalocean_', 'provider "digitalocean"'],
        'linode': ['linode_', 'provider "linode"'],
        'oracle': ['oci_', 'provider "oci"']
    }
    
    @classmethod
    def detect_providers(cls, tf_files: Dict[str, str], plan_data: Dict[str, Any] = None) -> List[str]:
        """Detect cloud providers from Terraform files or plan data (dynamically detects any provider)"""
        detected = set()
        
        # If we have Terraform files, analyse them
        if tf_files:
            for filepath, content in tf_files.items():
                content_lower = content.lower()
                # First check known providers with specific patterns
                for provider, patterns in cls.PROVIDER_PATTERNS.items():
                    if any(pattern in content_lower for pattern in patterns):
                        detected.add(provider)
        
        # Always check plan data for additional/unknown providers
        if plan_data:
            resource_changes = plan_data.get('resource_changes', [])
            for change in resource_changes:
                resource_type = change.get('type', '')
                if '_' in resource_type:
                    # Extract provider prefix (e.g., "datadog_monitor" -> "datadog")
                    provider_prefix = resource_type.split('_')[0]
                    
                    # Check if it matches a known provider pattern
                    matched_known = False
                    for known_provider, patterns in cls.PROVIDER_PATTERNS.items():
                        if any(pattern.rstrip('_') == provider_prefix for pattern in patterns if pattern.endswith('_')):
                            detected.add(known_provider)
                            matched_known = True
                            break
                    
                    # If not a known provider, add it dynamically
                    if not matched_known and provider_prefix not in ['data', 'module', 'var', 'local', 'output']:
                        detected.add(provider_prefix)
        
        return sorted(list(detected))
    
    @classmethod
    def get_primary_provider(cls, providers: List[str]) -> str:
        """Determine the primary provider"""
        if not providers:
            return "unknown"
        if len(providers) == 1:
            return providers[0]
        
        # Priority order for multi-provider setups
        priority = ['aws', 'azure', 'gcp', 'kubernetes']
        for p in priority:
            if p in providers:
                return p
        
        return providers[0]


class TerraformMCPClient:
    """Real MCP client for HashiCorp Terraform MCP Server using proper MCP protocol"""
    
    def __init__(self):
        self.available = False
        self.process = None
        self.initialized = False
        self.mcp_mode = os.environ.get('MCP_AVAILABLE', 'false')
        self._setup_client()
    
    def _setup_client(self):
        """Setup MCP client based on availability mode"""
        if self.mcp_mode == 'true':
            # Primary mode: stdio protocol
            self.available = True
            print("MCP client configured for stdio protocol")
        else:
            # Disabled or failed
            self.available = False
            print("Warning: MCP client disabled - no server available")
    

    
    async def _start_mcp_process(self):
        """Start MCP server process using Docker stdio transport"""
        if self.mcp_mode != 'true':
            return False
            
        try:
            # The HashiCorp MCP server runs on stdio by default (no 'stdio' command needed)
            cmd = [
                'docker', 'run', '--rm', '-i',
                'hashicorp/terraform-mcp-server:1.2.0'
            ]
            
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            return True
        except Exception as e:
            print(f"Warning: Could not start MCP stdio process: {e}", file=sys.stderr)
            return False
    
    async def _send_mcp_request(self, method: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Send proper MCP JSON-RPC request"""
        
        # Handle stdio mode
        if not self.process:
            return None
            
        request = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method
        }
        
        if params:
            request["params"] = params
        
        try:
            request_json = json.dumps(request) + '\n'
            self.process.stdin.write(request_json.encode())
            await self.process.stdin.drain()
            
            response_line = await asyncio.wait_for(
                self.process.stdout.readline(), 
                timeout=20.0  # Increased timeout for provider searches
            )
            
            if response_line:
                response_text = response_line.decode().strip()
                if response_text:
                    return json.loads(response_text)
                    
        except asyncio.TimeoutError:
            print(f"Warning: MCP request timeout for method '{method}'", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON response from MCP server for '{method}': {e}", file=sys.stderr)
        except Exception as e:
            if str(e):  # Only print if there's an actual error message
                print(f"Warning: MCP request failed for '{method}': {e}", file=sys.stderr)
            else:
                print(f"Warning: MCP request failed for '{method}' (no error details)", file=sys.stderr)
            return None
        
        return None
    

    
    async def _initialize_mcp(self) -> bool:
        """Initialize proper MCP connection"""
        if self.mcp_mode != 'true':
            return False
            
        if not await self._start_mcp_process():
            return False
        
        response = await self._send_mcp_request("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {
                "name": "terraform-ai-checker",
                "version": "1.0.0"
            }
        })
        
        if response and "result" in response:
            self.initialized = True
            print("MCP stdio connection initialized successfully")
            return True
        else:
            print("Warning: MCP stdio initialization failed, falling back to HTTP", file=sys.stderr)
            return False
    
    async def _get_provider_insights_mcp(self, providers: List[str]) -> Dict[str, Any]:
        """Get real provider insights using proper MCP protocol"""
        insights = {}
        
        # Map common provider names to actual registry names
        provider_name_mapping = {
            "azure": "azurerm",  # Our detector uses 'azure' but registry uses 'azurerm'
            "gcp": "google",     # Our detector uses 'gcp' but registry uses 'google'
        }
        
        for provider in providers[:3]:  # Limit to avoid timeout
            # Use mapped name if available, otherwise use original
            registry_provider_name = provider_name_mapping.get(provider, provider)
            
            try:
                # Real MCP call to resolve provider documentation
                # Use specific resource types that work well for each provider
                resource_mapping = {
                    "azurerm": "resource_group",  # Known to work for Azure
                    "aws": "instance",            # Common AWS resource
                    "google": "compute_instance", # Common GCP resource
                }
                service_slug = resource_mapping.get(registry_provider_name, registry_provider_name)
                
                response = await self._send_mcp_request("tools/call", {
                    "name": "search_providers",
                    "arguments": {
                        "provider_name": registry_provider_name,
                        "provider_namespace": "hashicorp", 
                        "service_slug": service_slug,
                        "provider_data_type": "resources"
                    }
                })
                
                if response and "result" in response:
                    content = response["result"].get("content", [])
                    if content:
                        insights[provider] = {
                            "status": "available",
                            "documentation_available": True,
                            "doc_count": len(content)
                        }
                    else:
                        insights[provider] = {"status": "limited", "documentation_available": False}
                else:
                    # Only log if we care about missing provider docs
                    if provider in ["aws", "azurerm", "google"]:  # Major providers
                        print(f"Note: No documentation found for provider '{provider}'", file=sys.stderr)
                    insights[provider] = {"status": "unavailable"}
                    
            except Exception as e:
                print(f"Warning: MCP provider insight failed for {provider}: {e}", file=sys.stderr)
                insights[provider] = {"status": "error", "error": str(e)}
        
        return insights
    
    async def _search_modules_mcp(self, providers: List[str]) -> List[Dict]:
        """Search modules using proper MCP protocol"""
        module_suggestions = []
        
        # Map common provider names to actual registry names
        provider_name_mapping = {
            "azure": "azurerm",  # Our detector uses 'azure' but registry uses 'azurerm'
            "gcp": "google",     # Our detector uses 'gcp' but registry uses 'google'
        }
        
        for provider in providers[:2]:  # Limit searches
            # Use mapped name if available, otherwise use original
            registry_provider_name = provider_name_mapping.get(provider, provider)
            
            try:
                response = await self._send_mcp_request("tools/call", {
                    "name": "search_modules",
                    "arguments": {
                        "module_query": registry_provider_name,
                        "current_offset": 0
                    }
                })
                
                if response and "result" in response:
                    content = response["result"].get("content", [])
                    if content and len(content) > 0:
                        try:
                            # Parse module results
                            modules_text = content[0].get("text", "")
                            if modules_text and "modules found" in modules_text:
                                module_suggestions.append({
                                    "provider": provider,
                                    "modules": [{"name": f"{provider}-module-example", "description": f"Example {provider} module"}],
                                    "total_found": 1
                                })
                        except Exception:
                            pass
                            
            except Exception as e:
                print(f"Warning: MCP module search failed for {provider}: {e}", file=sys.stderr)
        
        return module_suggestions
    
    async def _get_resource_specific_docs(self, plan_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed documentation for specific resources in the plan"""
        resource_docs = {}
        
        resource_changes = plan_data.get("resource_changes", [])
        unique_resources = set()
        
        # Extract unique resource types from plan
        for change in resource_changes:
            resource_type = change.get("type", "")
            if resource_type and resource_type not in unique_resources:
                unique_resources.add(resource_type)
        
        # Get documentation for each resource type (limit to avoid timeouts)
        for resource_type in list(unique_resources)[:5]:
            try:
                # Extract provider and service from resource type
                provider_name = resource_type.split("_")[0] if "_" in resource_type else resource_type
                service_slug = resource_type.replace(f"{provider_name}_", "") if "_" in resource_type else resource_type
                
                # Map provider names to registry names
                provider_mapping = {"azure": "azurerm", "gcp": "google"}
                registry_provider = provider_mapping.get(provider_name, provider_name)
                
                # Search for the specific resource documentation
                search_response = await self._send_mcp_request("tools/call", {
                    "name": "search_providers",
                    "arguments": {
                        "provider_name": registry_provider,
                        "provider_namespace": "hashicorp",
                        "service_slug": service_slug,
                        "provider_data_type": "resources"
                    }
                })
                
                if search_response and "result" in search_response:
                    content = search_response["result"].get("content", [])
                    if content:
                        # Extract provider_doc_id from the search results
                        first_result = content[0]
                        if isinstance(first_result, dict):
                            text = first_result.get("text", "")
                            
                            # Look for provider_doc_id in the text
                            import re
                            doc_id_matches = re.findall(r'providerDocID:\s*(\w+)', text)
                            
                            if doc_id_matches:
                                doc_id = doc_id_matches[0]  # Use first match
                                
                                # Get detailed documentation using the document ID
                                doc_response = await self._send_mcp_request("tools/call", {
                                    "name": "get_provider_details",
                                    "arguments": {
                                        "provider_doc_id": doc_id
                                    }
                                })
                                
                                if doc_response and "result" in doc_response:
                                    doc_content = doc_response["result"].get("content", [])
                                    if doc_content:
                                        # Extract documentation URL if available
                                        doc_text = doc_content[0].get("text", "") if doc_content else ""
                                        url_match = re.search(r'https://registry\.terraform\.io/providers/[^\s]+', doc_text)
                                        doc_url = url_match.group(0) if url_match else None
                                        
                                        resource_docs[resource_type] = {
                                            "documentation": doc_text[:1000],  # First 1000 chars
                                            "doc_id": doc_id,
                                            "url": doc_url,
                                            "status": "available"
                                        }
                            else:
                                resource_docs[resource_type] = {
                                    "search_result": text[:300],  # Store search result
                                    "status": "found_search_only"
                                }
                                
            except Exception as e:
                print(f"Warning: Could not get docs for {resource_type}: {e}", file=sys.stderr)
                resource_docs[resource_type] = {"status": "error", "error": str(e)}
        
        return resource_docs
    
    async def _get_version_compatibility(self, providers: List[str]) -> Dict[str, Any]:
        """Check provider version compatibility and get latest versions"""
        version_info = {}
        
        provider_mapping = {
            "azure": "azurerm",
            "gcp": "google"
        }
        
        for provider in providers[:3]:  # Limit to avoid timeouts
            registry_name = provider_mapping.get(provider, provider)
            try:
                response = await self._send_mcp_request("tools/call", {
                    "name": "get_latest_provider_version",
                    "arguments": {
                        "namespace": "hashicorp",
                        "name": registry_name
                    }
                })
                
                if response and "result" in response:
                    content = response["result"].get("content", [])
                    if content:
                        # Extract version information
                        version_text = content[0].get("text", "") if isinstance(content[0], dict) else str(content[0])
                        
                        # MCP server returns just the version number, try multiple patterns
                        import re
                        
                        # First try to find a clean semver pattern (which is what MCP returns)
                        version_patterns = [
                            r'^([0-9]+\.[0-9]+\.[0-9]+)$',  # Exact match for "4.46.0" format from MCP
                            r'([0-9]+\.[0-9]+\.[0-9]+)',    # Any semver in the text
                            r'version[:\s]*([0-9]+\.[0-9]+\.[0-9]+)',  # "version: x.y.z" format
                        ]
                        
                        latest_version = "unknown"
                        for pattern in version_patterns:
                            version_match = re.search(pattern, version_text.strip(), re.IGNORECASE)
                            if version_match:
                                latest_version = version_match.group(1)
                                break
                        
                        # Extract registry URL if available
                        url_match = re.search(r'https://registry\.terraform\.io/providers/[^\s]+', version_text)
                        registry_url = url_match.group(0) if url_match else f"https://registry.terraform.io/providers/hashicorp/{registry_name}"
                        
                        version_info[provider] = {
                            "latest_version": latest_version,
                            "registry_url": registry_url,
                            "status": "available",
                            "full_response": version_text[:500]  # Store first 500 chars for context
                        }
                        
            except Exception as e:
                print(f"Warning: Version check failed for {provider}: {e}", file=sys.stderr)
                version_info[provider] = {"status": "error", "error": str(e)}
        
        return version_info
    
    async def _cleanup_mcp(self):
        """Cleanup MCP process"""
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
    
    def validate_plan_with_mcp(self, plan_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point for MCP validation - handles async execution"""
        if not self.available:
            return {"validation_results": [], "recommendations": [], "mcp_status": "unavailable"}
            
        try:
            # Run async validation in a new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self._validate_plan_async(plan_data))
                return result
            finally:
                loop.close()
        except Exception as e:
            print(f"Warning: MCP validation failed: {e}", file=sys.stderr)
            return {"validation_results": [], "recommendations": [], "mcp_status": "failed"}
    
    async def _validate_plan_async(self, plan_data: Dict[str, Any]) -> Dict[str, Any]:
        """Async MCP validation with real protocol"""
        result = {
            "validation_results": [],
            "recommendations": [],
            "mcp_status": "disconnected",
            "provider_insights": {},
            "module_suggestions": [],
            "resource_documentation": {},
            "version_compatibility": {}
        }
        
        try:
            # Extract providers from plan
            providers = self._extract_providers_from_plan(plan_data)
            
            # Try stdio mode first if available
            if self.mcp_mode == 'true' and await self._initialize_mcp():
                result["mcp_status"] = "connected"
                
                # Get real provider insights using stdio
                if providers:
                    result["provider_insights"] = await self._get_provider_insights_mcp(providers)
                    result["module_suggestions"] = await self._search_modules_mcp(providers)
                    result["resource_documentation"] = await self._get_resource_specific_docs(plan_data)
                    result["version_compatibility"] = await self._get_version_compatibility(providers)
                
                # Create validation results from insights
                validation_results = []
                for provider, insights in result["provider_insights"].items():
                    if insights.get("status") == "available":
                        validation_results.append({
                            "rule": f"{provider.upper()} Provider Documentation",
                            "status": "pass",
                            "message": f"Documentation available with {insights.get('doc_count', 0)} resources"
                        })
                    elif insights.get("status") == "limited":
                        validation_results.append({
                            "rule": f"{provider.upper()} Provider Documentation",
                            "status": "warn",
                            "message": "Limited documentation available"
                        })
                
                result["validation_results"] = validation_results
                

            else:
                result["mcp_status"] = "unavailable"
                
        except Exception as e:
            print(f"Warning: MCP async validation error: {e}", file=sys.stderr)
            result["mcp_status"] = "error"
        finally:
            await self._cleanup_mcp()
        
        return result
    
    def _extract_providers_from_plan(self, plan_data: Dict[str, Any]) -> List[str]:
        """Extract provider names from plan data"""
        providers = set()
        resource_changes = plan_data.get("resource_changes", [])
        
        for change in resource_changes:
            resource_type = change.get("type", "")
            if "_" in resource_type:
                provider = resource_type.split("_")[0]
                providers.add(provider)
        
        return list(providers)


class AIProvider:
    """Base interface implemented by each supported AI provider.

    Every provider isolates its client construction, model-name resolution, and
    request/response shape in one place, so adding a provider is a single new
    class + registry entry rather than a scattered set of if/elif branches.
    """

    def init_client(self, config: AnalysisConfig):
        raise NotImplementedError

    def model_name(self, config: AnalysisConfig) -> str:
        return config.azure_openai_deployment

    def complete(self, client, model: str, system_content: str, user_content: str,
                 temperature: float, max_tokens: int, timeout_seconds: int) -> str:
        raise NotImplementedError


class AzureOpenAIProvider(AIProvider):
    """OpenAI-compatible models (e.g. GPT-5 family) on Microsoft Foundry, via the v1 API.

    The v1 API removes the need for a dated `api-version` parameter: the OpenAI
    client is pointed at `<endpoint>/openai/v1/` instead of using AzureOpenAI().
    """

    def init_client(self, config: AnalysisConfig):
        from openai import OpenAI
        base_url = config.azure_openai_endpoint.rstrip('/') + '/openai/v1/'
        return OpenAI(api_key=config.azure_openai_api_key, base_url=base_url)

    def complete(self, client, model, system_content, user_content, temperature, max_tokens, timeout_seconds):
        # GPT-5 family models are reasoning models: they use max_completion_tokens
        # instead of max_tokens, and reject temperature/presence_penalty/frequency_penalty
        # overrides (only the default value of each is accepted).
        is_gpt5 = 'gpt-5' in model.lower()

        api_params = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            "timeout": timeout_seconds
        }
        if is_gpt5:
            api_params["max_completion_tokens"] = max_tokens
        else:
            api_params["temperature"] = temperature
            api_params["presence_penalty"] = 0.1  # Reduce repetition
            api_params["frequency_penalty"] = 0.1  # Encourage diverse language
            api_params["max_tokens"] = max_tokens

        response = client.chat.completions.create(**api_params)
        return response.choices[0].message.content


class AzureAnthropicProvider(AIProvider):
    """Claude models on Microsoft Foundry, via the native Anthropic Messages API.

    Claude on Foundry is not exposed through the OpenAI-compatible endpoint - it's
    called through the Anthropic Messages API at `<endpoint>/anthropic`, using the
    `anthropic` package's AnthropicFoundry client (same Azure resource, different
    request/response shape: top-level `system`, `content` blocks in the response).
    """

    def init_client(self, config: AnalysisConfig):
        from anthropic import AnthropicFoundry
        base_url = config.azure_openai_endpoint.rstrip('/') + '/anthropic'
        return AnthropicFoundry(api_key=config.azure_openai_api_key, base_url=base_url)

    def complete(self, client, model, system_content, user_content, temperature, max_tokens, timeout_seconds):
        message = client.messages.create(
            model=model,
            system=system_content,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout_seconds
        )
        return "".join(block.text for block in message.content if getattr(block, "type", None) == "text")


PROVIDERS: Dict[str, AIProvider] = {
    "azure": AzureOpenAIProvider(),
    "azure-anthropic": AzureAnthropicProvider(),
}


class TerraformAnalyser:
    """Main Terraform analysis class"""

    def __init__(self, config: AnalysisConfig):
        self.config = config
        self._validate_inputs()  # Validate all inputs before processing
        self.mcp_client = TerraformMCPClient() if not config.skip_mcp else None
        self.provider = PROVIDERS[self.config.ai_provider]
        self.ai_client = self._init_ai_client()

    def _init_ai_client(self):
        """Initialize the AI client for the configured provider"""
        try:
            return self.provider.init_client(self.config)
        except ImportError as e:
            print(f"Error: required package not found for provider '{self.config.ai_provider}': {e}")
            sys.exit(1)
    
    def _validate_path(self, path: str, base_dir: str = os.getcwd()) -> str:
        """Validate and resolve path to prevent traversal attacks (CWE-22)
        
        Args:
            path: User-provided path (relative or absolute)
            base_dir: Base directory to restrict access to
            
        Returns:
            Validated absolute path
            
        Raises:
            ValueError: If path escapes base directory
        """
        # Resolve to absolute path
        if os.path.isabs(path):
            abs_path = os.path.abspath(path)
        else:
            abs_path = os.path.abspath(os.path.join(base_dir, path))
        
        abs_base = os.path.abspath(base_dir)
        
        # Ensure path is within base directory
        if not abs_path.startswith(abs_base + os.sep) and abs_path != abs_base:
            raise ValueError(
                f"Security Error: Path '{path}' attempts to access files outside allowed directory. "
                f"Allowed: {abs_base}, Requested: {abs_path}"
            )
        
        return abs_path
    
    def _validate_inputs(self) -> None:
        """Validate all configuration inputs to prevent injection attacks"""
        
        # Validate AI provider
        if self.config.ai_provider not in PROVIDERS:
            raise ValueError(
                f"Invalid AI provider '{self.config.ai_provider}'. "
                f"Must be one of: {', '.join(PROVIDERS.keys())}"
            )

        # Validate required credentials - all providers currently run on the
        # same Microsoft Foundry resource (endpoint + key)
        if not self.config.azure_openai_api_key:
            raise ValueError(f"Azure OpenAI API key is required when using '{self.config.ai_provider}' provider")
        if not self.config.azure_openai_endpoint:
            raise ValueError(f"Azure OpenAI endpoint is required when using '{self.config.ai_provider}' provider")
        
        # Validate paths (prevent path traversal)
        workspace_dir = os.getcwd()
        
        # Validate terraform directory
        try:
            self.config.terraform_directory = self._validate_path(
                self.config.terraform_directory, 
                workspace_dir
            )
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        
        # Validate plan path
        try:
            self.config.terraform_plan_path = self._validate_path(
                self.config.terraform_plan_path,
                workspace_dir
            )
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        
        # Validate plan file exists and is valid JSON
        if not os.path.exists(self.config.terraform_plan_path):
            raise ValueError(f"Terraform plan file not found: {self.config.terraform_plan_path}")
        
        # Validate plan file is valid JSON with correct format
        try:
            with open(self.config.terraform_plan_path, 'r') as f:
                plan = json.load(f)
                if 'format_version' not in plan:
                    raise ValueError(
                        "Invalid Terraform plan format: missing 'format_version' field. "
                        "Ensure you're using 'terraform show -json' output."
                    )
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in Terraform plan file: {e}")
        
        # Validate analysis preset if provided
        allowed_presets = ['security-audit', 'cost-optimisation', 'production-ready', 
                          'quick-check', 'complete', '']
        analysis_preset = getattr(self.config, 'analysis_preset', '')
        if analysis_preset and analysis_preset not in allowed_presets:
            raise ValueError(
                f"Invalid analysis preset '{analysis_preset}'. "
                f"Must be one of: {', '.join([p for p in allowed_presets if p])}"
            )
        
        # Validate analysis mode
        allowed_modes = ['plan-only', 'comprehensive']
        if self.config.analysis_mode not in allowed_modes:
            raise ValueError(
                f"Invalid analysis mode '{self.config.analysis_mode}'. "
                f"Must be one of: {', '.join(allowed_modes)}"
            )
        
        # Validate analysis style
        allowed_styles = ['severity', 'domain']
        if self.config.analysis_style not in allowed_styles:
            raise ValueError(
                f"Invalid analysis style '{self.config.analysis_style}'. "
                f"Must be one of: {', '.join(allowed_styles)}"
            )
        
        print("✅ Input validation passed")
    
    def _scrub_sensitive_data(self, data: str) -> str:
        """Redact sensitive data patterns before sending to AI (CWE-200 mitigation)
        
        Args:
            data: Text that may contain sensitive information
            
        Returns:
            Scrubbed text with sensitive patterns redacted
        """
        # Check if scrubbing is enabled (default: true for security)
        if os.environ.get('SCRUB_SENSITIVE_DATA', 'true').lower() == 'false':
            print("Warning: Sensitive data scrubbing is disabled", file=sys.stderr)
            return data
        
        # Patterns to redact (case-insensitive)
        patterns = [
            # Passwords
            (r'password\s*=\s*"[^"]*"', 'password = "***REDACTED***"'),
            (r'password\s*=\s*\'[^\']*\'', 'password = \'***REDACTED***\''),
            (r'"password"\s*:\s*"[^"]*"', '"password": "***REDACTED***"'),
            
            # API Keys and tokens
            (r'api_key\s*=\s*"[^"]*"', 'api_key = "***REDACTED***"'),
            (r'api_key\s*=\s*\'[^\']*\'', 'api_key = \'***REDACTED***\''),
            (r'token\s*=\s*"[^"]*"', 'token = "***REDACTED***"'),
            (r'access_key\s*=\s*"[^"]*"', 'access_key = "***REDACTED***"'),
            (r'secret_key\s*=\s*"[^"]*"', 'secret_key = "***REDACTED***"'),
            (r'client_secret\s*=\s*"[^"]*"', 'client_secret = "***REDACTED***"'),
            
            # Generic secrets
            (r'secret\s*=\s*"[^"]*"', 'secret = "***REDACTED***"'),
            (r'"secret"\s*:\s*"[^"]*"', '"secret": "***REDACTED***"'),
            
            # Connection strings (may contain credentials)
            (r'connection_string\s*=\s*"[^"]*"', 'connection_string = "***REDACTED***"'),
            (r'jdbc_url\s*=\s*"[^"]*"', 'jdbc_url = "***REDACTED***"'),
            
            # Private/internal IP addresses (RFC 1918)
            (r'\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '10.x.x.x'),
            (r'\b172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}\b', '172.x.x.x'),
            (r'\b192\.168\.\d{1,3}\.\d{1,3}\b', '192.168.x.x'),
            
            # AWS-style access keys (example pattern)
            (r'AKIA[0-9A-Z]{16}', 'AKIA***REDACTED***'),
            
            # Generic base64-encoded secrets (40+ chars that look like secrets)
            (r'["\']([A-Za-z0-9+/]{40,}={0,2})["\']', '"***REDACTED_BASE64***"'),
        ]
        
        scrubbed_data = data
        redaction_count = 0
        
        for pattern, replacement in patterns:
            matches = re.findall(pattern, scrubbed_data, flags=re.IGNORECASE)
            if matches:
                redaction_count += len(matches)
            scrubbed_data = re.sub(pattern, replacement, scrubbed_data, flags=re.IGNORECASE)
        
        if redaction_count > 0:
            print(f"🔒 Scrubbed {redaction_count} sensitive data patterns before AI analysis")
        
        return scrubbed_data
    
    def read_terraform_files(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Read all Terraform files and detect changed files with size limits"""
        all_tf_files = {}
        changed_tf_files = {}
        
        # Skip file reading in plan-only mode
        if self.config.analysis_mode == "plan-only":
            print("Plan-only mode: Skipping Terraform file reading")
            return all_tf_files, changed_tf_files
        
        # File size limits (configurable via environment)
        max_file_size = int(os.environ.get('MAX_FILE_SIZE_MB', '1')) * 1_000_000  # Default 1MB per file
        max_total_size = int(os.environ.get('MAX_TOTAL_SIZE_MB', '10')) * 1_000_000  # Default 10MB total
        max_files = int(os.environ.get('MAX_FILES', '100'))  # Default 100 files
        
        total_size = 0
        file_count = 0
        
        # Read all .tf files in the specified directory (already validated)
        tf_pattern = os.path.join(self.config.terraform_directory, "**/*.tf")
        
        for tf_file in glob.glob(tf_pattern, recursive=True):
            # Skip hidden files
            if os.path.basename(tf_file).startswith('.'):
                continue
            
            # Check file count limit
            if file_count >= max_files:
                print(f"Warning: Reached maximum file limit ({max_files}), skipping remaining files", file=sys.stderr)
                break
            
            # Validate file is within allowed directory (extra safety check)
            try:
                validated_path = self._validate_path(tf_file, self.config.terraform_directory)
            except ValueError as e:
                print(f"Warning: Skipping file due to path validation: {e}", file=sys.stderr)
                continue
            
            # Check file size
            try:
                file_size = os.path.getsize(validated_path)
            except OSError as e:
                print(f"Warning: Could not get size of {tf_file}: {e}", file=sys.stderr)
                continue
            
            # Skip files that are too large
            if file_size > max_file_size:
                print(f"Warning: Skipping large file: {tf_file} ({file_size} bytes exceeds {max_file_size} limit)", file=sys.stderr)
                continue
            
            # Check total size limit
            if total_size + file_size > max_total_size:
                print(f"Warning: Reached total size limit ({max_total_size} bytes), skipping remaining files", file=sys.stderr)
                break
            
            # Read file
            try:
                with open(validated_path, 'r', encoding='utf-8') as f:
                    rel_path = os.path.relpath(validated_path, self.config.terraform_directory)
                    all_tf_files[rel_path] = f.read()
                    total_size += file_size
                    file_count += 1
            except Exception as e:
                print(f"Warning: Could not read {tf_file}: {e}", file=sys.stderr)
        
        print(f"Read {file_count} Terraform files ({total_size} bytes total)")
        
        # Read changed Terraform files if they exist
        changed_dir = "changed_terraform"
        if os.path.exists(changed_dir):
            for tf_file in glob.glob(f"{changed_dir}/*.tf"):
                filename = os.path.basename(tf_file)
                try:
                    # Validate path
                    validated_path = self._validate_path(tf_file, changed_dir)
                    
                    # Check file size
                    file_size = os.path.getsize(validated_path)
                    if file_size > max_file_size:
                        print(f"Warning: Skipping large changed file: {tf_file} ({file_size} bytes)", file=sys.stderr)
                        continue
                    
                    with open(validated_path, 'r', encoding='utf-8') as f:
                        changed_tf_files[filename] = f.read()
                except Exception as e:
                    print(f"Warning: Could not read changed file {tf_file}: {e}", file=sys.stderr)
        
        return all_tf_files, changed_tf_files
    
    def format_plan_changes(self, plan_data: Dict[str, Any]) -> Tuple[List[Dict], List[str], Dict[str, int]]:
        """Format plan changes for analysis"""
        resource_changes = plan_data.get('resource_changes', [])
        
        formatted_changes = []
        resource_types = set()
        action_counts = {'create': 0, 'update': 0, 'delete': 0, 'replace': 0, 'no-op': 0}
        
        for change in resource_changes:
            actions = change.get('change', {}).get('actions', ['no-op'])
            primary_action = actions[0] if actions else 'no-op'
            
            # Count actions
            if 'create' in actions:
                action_counts['create'] += 1
            if 'update' in actions:
                action_counts['update'] += 1
            if 'delete' in actions:
                action_counts['delete'] += 1
            if ['delete', 'create'] == actions:
                action_counts['replace'] += 1
                primary_action = 'replace'
            if primary_action == 'no-op':
                action_counts['no-op'] += 1
            
            if primary_action != 'no-op':
                resource_type = change.get('type', 'unknown')
                resource_name = change.get('name', 'unknown')
                address = change.get('address', 'unknown')
                
                resource_types.add(resource_type)
                
                before = change.get('change', {}).get('before')
                after = change.get('change', {}).get('after')
                
                change_details = {
                    'action': primary_action,
                    'resource': f"{resource_type}.{resource_name}",
                    'address': address,
                    'resource_type': resource_type,
                    'before': before,
                    'after': after
                }
                
                formatted_changes.append(change_details)
        
        return formatted_changes, list(resource_types), action_counts
    
    def create_analysis_prompt(self, tf_files: Dict[str, str], changed_files: Dict[str, str], 
                             plan_changes: List[Dict], resource_types: List[str], 
                             action_counts: Dict[str, int], providers: List[str],
                             mcp_insights: Optional[Dict[str, Any]] = None) -> str:
        """Create the analysis prompt for OpenAI with optional MCP insights integration and data scrubbing"""
        
        primary_provider = CloudProviderDetector.get_primary_provider(providers)
        provider_context = f"**Detected Providers:** {', '.join(providers) if providers else 'Unknown (plan-only mode)'}\n"
        provider_context += f"**Primary Provider:** {primary_provider.upper()}\n\n"
        
        # Determine context based on analysis mode and available data
        if self.config.analysis_mode == "plan-only":
            context_description = "This analysis focuses on reviewing the Terraform plan JSON output only. Source files were not analysed for faster execution."
            tf_context = "### Analysis Mode: Plan-Only\n\n"
            tf_context += "**Note:** This analysis is based solely on the Terraform plan JSON. For more comprehensive analysis including source file review, use 'comprehensive' mode.\n\n"
        elif changed_files:
            context_description = "This comprehensive analysis reviews both the Terraform plan and the changed source files."
            tf_context = "### Changed Terraform Files:\n\n"
            for filename, content in changed_files.items():
                # Scrub sensitive data from file content before adding to prompt
                scrubbed_content = self._scrub_sensitive_data(content)
                tf_context += f"**{filename}:**\n```hcl\n{scrubbed_content[:2000]}{'...' if len(scrubbed_content) > 2000 else ''}\n```\n\n"
        else:
            context_description = "This comprehensive analysis reviews both the Terraform plan and the overall configuration."
            tf_context = "### Terraform Configuration:\n\n"
            for filepath, content in list(tf_files.items())[:5]:  # Limit to first 5 files
                # Scrub sensitive data from file content before adding to prompt
                scrubbed_content = self._scrub_sensitive_data(content)
                tf_context += f"**{filepath}:**\n```hcl\n{scrubbed_content[:1500]}{'...' if len(scrubbed_content) > 1500 else ''}\n```\n\n"
            if len(tf_files) > 5:
                tf_context += f"*... and {len(tf_files) - 5} more files*\n\n"
        
        # Format plan changes
        plan_summary = f"### Plan Summary:\n"
        plan_summary += f"- **Create:** {action_counts['create']} resources\n"
        plan_summary += f"- **Update:** {action_counts['update']} resources\n" 
        plan_summary += f"- **Delete:** {action_counts['delete']} resources\n"
        plan_summary += f"- **Replace:** {action_counts['replace']} resources\n\n"
        
        plan_text = "### Detailed Plan Changes:\n\n"
        if not plan_changes:
            plan_text += "No resource changes detected in the plan.\n\n"
        else:
            for change in plan_changes[:10]:  # Limit to first 10 changes
                plan_text += f"**Action:** {change['action']}\n"
                plan_text += f"**Resource:** {change['resource']}\n"
                plan_text += f"**Address:** {change['address']}\n"
                if change['before'] and change['action'] in ['update', 'replace']:
                    plan_text += f"**Configuration changes detected**\n"
                plan_text += "\n---\n\n"
            if len(plan_changes) > 10:
                plan_text += f"*... and {len(plan_changes) - 10} more changes*\n\n"
        
        # Create focus areas prompt
        focus_areas = []
        if 'security' in self.config.analysis_focus:
            focus_areas.append("**Security Analysis**: Identify security vulnerabilities, exposed resources, and compliance issues")
        if 'cost' in self.config.analysis_focus:
            focus_areas.append("**Cost Impact**: Analyse cost implications and optimisation opportunities")
        if 'best-practices' in self.config.analysis_focus:
            focus_areas.append("**Best Practices**: Review adherence to infrastructure and provider-specific best practices")
        if 'deployment' in self.config.analysis_focus:
            focus_areas.append("**Deployment Readiness**: Assess deployment safety and potential risks")
        if 'compliance' in self.config.analysis_focus:
            focus_areas.append("**Compliance**: Check for regulatory and organisational compliance requirements")
        if 'performance' in self.config.analysis_focus:
            focus_areas.append("**Performance**: Analyse resource sizing, scaling policies, and performance optimisation")
        if 'reliability' in self.config.analysis_focus:
            focus_areas.append("**Reliability**: Review high availability, disaster recovery, and fault tolerance")
        if 'observability' in self.config.analysis_focus:
            focus_areas.append("**Observability**: Examine logging, monitoring, alerting, and tracing configurations")
        if 'networking' in self.config.analysis_focus:
            focus_areas.append("**Networking**: Assess network security, connectivity, routing, and firewall rules")
        if 'data' in self.config.analysis_focus:
            focus_areas.append("**Data**: Evaluate data protection, encryption, backup strategies, and storage optimisation")
        if 'governance' in self.config.analysis_focus:
            focus_areas.append("**Governance**: Check resource tagging, naming conventions, and organisational policies")
        
        focus_text = "\n".join(focus_areas)
        
        # Provider-specific guidance
        provider_guidance = ""
        if primary_provider == 'aws':
            provider_guidance = "\nFocus on AWS-specific concerns: IAM permissions, VPC security, S3 bucket policies, and AWS service limits."
        elif primary_provider == 'azure':
            provider_guidance = "\nFocus on Azure-specific concerns: Resource groups, RBAC, Network Security Groups, and Azure policy compliance."
        elif primary_provider == 'gcp':
            provider_guidance = "\nFocus on GCP-specific concerns: IAM bindings, VPC firewall rules, service accounts, and GCP organisation policies."
        elif primary_provider == 'kubernetes':
            provider_guidance = "\nFocus on Kubernetes concerns: RBAC, network policies, resource quotas, and security contexts."
        
        # Add MCP insights from HashiCorp registry if available
        mcp_context = ""
        if mcp_insights and mcp_insights.get("mcp_status") == "connected":
            mcp_context += "\n### Terraform Registry Insights (via HashiCorp MCP Server):\n\n"
            
            # Provider documentation status and version compatibility
            provider_insights = mcp_insights.get("provider_insights", {})
            version_info = mcp_insights.get("version_compatibility", {})
            
            if provider_insights or version_info:
                mcp_context += "**LATEST PROVIDER VERSIONS (Use these in your analysis):**\n"
                for provider in set(list(provider_insights.keys()) + list(version_info.keys())):
                    insights = provider_insights.get(provider, {})
                    version = version_info.get(provider, {})
                    
                    doc_status = "✅" if insights.get("status") == "available" else "❌"
                    doc_count = insights.get("doc_count", 0)
                    latest_version = version.get("latest_version", "unknown")
                    registry_url = version.get("registry_url", "")
                    
                    version_link = f" ([Registry]({registry_url}))" if registry_url else ""
                    version_display = f"v{latest_version}" if latest_version and latest_version not in ["unknown", "check registry"] else latest_version
                    mcp_context += f"- **{provider.upper()}**: {doc_status} {doc_count} resources | **LATEST: {version_display}**{version_link}\n"
                mcp_context += "\n**IMPORTANT:** When recommending provider version updates, reference these LATEST versions above.\n\n"
            
            # Resource-specific documentation
            resource_docs = mcp_insights.get("resource_documentation", {})
            if resource_docs:
                mcp_context += "**Resource-Specific Documentation:**\n"
                for resource_type, doc_info in resource_docs.items():
                    status = doc_info.get("status", "unknown")
                    if status == "available":
                        doc_url = doc_info.get("url", "")
                        url_link = f" ([Docs]({doc_url}))" if doc_url else ""
                        mcp_context += f"- `{resource_type}`: ✅ Detailed documentation available{url_link}\n"
                    elif status == "found_search_only":
                        mcp_context += f"- `{resource_type}`: ⚠️ Basic documentation found\n"
                    else:
                        mcp_context += f"- `{resource_type}`: ❌ Documentation unavailable\n"
                mcp_context += "\n"
            
            # Available modules
            module_suggestions = mcp_insights.get("module_suggestions", [])
            if module_suggestions:
                mcp_context += "**Available Terraform Modules:**\n"
                for suggestion in module_suggestions:
                    provider = suggestion.get("provider", "")
                    modules = suggestion.get("modules", [])
                    total = suggestion.get("total_found", 0)
                    if modules:
                        mcp_context += f"- {provider.upper()} Provider ({total} modules available):\n"
                        for module in modules[:3]:  # Show first 3 modules
                            name = module.get("name", "")
                            description = module.get("description", "")
                            # Create registry link for modules
                            module_url = f"https://registry.terraform.io/modules/{name}" if "/" in name else ""
                            url_link = f" ([Registry]({module_url}))" if module_url else ""
                            mcp_context += f"  - `{name}`: {description}{url_link}\n"
                        if len(modules) > 3:
                            mcp_context += f"  - ... and {len(modules) - 3} more modules\n"
                mcp_context += "\n"
            
            # Enhanced AI instructions with documentation referencing
            mcp_context += "**Enhanced Analysis Instructions:**\n"
            mcp_context += "- Use the provider version information to recommend upgrades if needed\n"
            mcp_context += "- Reference specific resource documentation for detailed configuration advice\n"
            mcp_context += "- Include documentation links in your recommendations when referencing registry content\n"
            mcp_context += "- Provide specific, registry-backed recommendations rather than generic advice\n"
            mcp_context += "- When suggesting modules or configurations, reference the provided registry URLs\n\n"
        
        # Determine analysis depth instructions
        analysis_depth = self.config.analysis_depth
        depth_instruction = ""
        if analysis_depth == 'quick':
            depth_instruction = "Provide a focused analysis highlighting the most critical issues and essential recommendations. Be concise but thorough on high-impact items."
        elif analysis_depth == 'detailed':
            depth_instruction = "Provide an exhaustive analysis with detailed explanations, comprehensive recommendations, and extensive context for each finding. Include learning opportunities and advanced optimisation suggestions."
        else:  # standard
            depth_instruction = "Provide a balanced analysis covering all significant issues with practical recommendations and clear explanations."

        return f"""
You are a senior DevOps and cloud infrastructure expert with extensive experience in Terraform, cloud security, and infrastructure best practices. {context_description}

{provider_context}

**Analysis Scope:**
{focus_text}

{provider_guidance}

{mcp_context}

## ANALYSIS METHODOLOGY
1. **Security Assessment**: Identify vulnerabilities, exposed resources, misconfigurations
2. **Risk Evaluation**: Assess deployment risks, breaking changes, data loss potential
3. **Optimisation Review**: Find cost savings, performance improvements, best practices
4. **Compliance Check**: Verify adherence to standards and policies
5. **Operational Readiness**: Evaluate monitoring, logging, backup, disaster recovery

## ANALYSIS DEPTH
{depth_instruction}

## INFRASTRUCTURE DATA

{tf_context}

{plan_summary}

{plan_text}

**Resource Types:** {', '.join(resource_types) if resource_types else 'None'}

## OUTPUT REQUIREMENTS
Provide a structured analysis with:

1. **Summary** - Key findings and overall risk assessment
2. **Quick Reference Table** - Summary table with: Domain | Resources | Issue/Opportunity | Link
3. **Critical Issues** (🔴) - Security vulnerabilities, breaking changes, data risks
4. **Warnings** (🟡) - Suboptimal configurations, potential issues
5. **Recommendations** (🔵) - Best practice improvements, optimisations
6. **Good Practices** (✅) - Correctly configured items to acknowledge

**QUICK REFERENCE TABLE FORMAT:**
Include a markdown table after the summary with these columns:
- **Domain**: security, compliance, cost, performance, version, etc.
- **Resources**: Specific terraform resource names affected (e.g., `aws_s3_bucket.main`)  
- **Issue/Opportunity**: Brief description (e.g., "Public access enabled", "Provider version outdated")
- **Link**: Terraform documentation link for the resource type

For each finding:
- Specify exact resource names (e.g., `aws_instance.web_server`)
- Explain the impact and risk level clearly
- Provide specific, actionable remediation steps
- Include relevant documentation links when available
- Estimate implementation effort where helpful

Be practical and specific rather than generic. Focus on actionable insights that will genuinely help improve the infrastructure.
"""
    
    def load_system_prompt(self, prompt_type: str = 'severity') -> str:
        """Load system prompt from file"""
        # Try to load from prompts directory (GitHub Action path or local)
        prompt_paths = [
            f"prompts/system_prompt_{prompt_type}.md",  # Local execution
            f"{os.path.dirname(__file__)}/prompts/system_prompt_{prompt_type}.md",  # Script directory
            f"{os.environ.get('GITHUB_ACTION_PATH', '.')}/prompts/system_prompt_{prompt_type}.md"  # GitHub Action
        ]
        
        for prompt_path in prompt_paths:
            if os.path.exists(prompt_path):
                try:
                    with open(prompt_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        print(f"Loaded system prompt from: {prompt_path}")
                        return content
                except Exception as e:
                    print(f"Warning: Could not read prompt file {prompt_path}: {e}", file=sys.stderr)
        
        # Fallback to default prompt if file not found
        print(f"Warning: Could not find prompt file for type '{prompt_type}', using fallback", file=sys.stderr)
        return self._get_fallback_prompt(prompt_type)
    
    def _get_fallback_prompt(self, prompt_type: str) -> str:
        """Fallback prompts if files are not found"""
        if prompt_type == 'domain':
            return """You are a senior DevOps engineer and cloud infrastructure expert specializing in Terraform and infrastructure as code.
Provide detailed, actionable analysis focusing on security, best practices, and deployment safety.
Group your findings by domain areas. Include severity levels: 🔴 Critical, 🟡 Warning, 🔵 Recommendation, ✅ Good Practice"""
        else:  # severity
            return """You are a senior DevOps engineer and cloud infrastructure expert specializing in Terraform and infrastructure as code.
Provide detailed, actionable analysis focusing on security, best practices, and deployment safety.
Group findings by severity level. Include severity levels: 🔴 Critical, 🟡 Warning, 🔵 Recommendation, ✅ Good Practice"""
    
    def analyse_with_ai(self, prompt: str) -> str:
        """Analyse the Terraform plan using the configured AI provider with retry logic"""
        # Scrub sensitive data from prompt before sending to AI
        scrubbed_prompt = self._scrub_sensitive_data(prompt)

        # Validate prompt size to avoid token limits
        prompt_length = len(scrubbed_prompt)
        if prompt_length > 100000:  # Rough estimate for token limits
            print(f"Warning: Large prompt detected ({prompt_length} chars). Consider using plan-only mode for better performance.")

        model_name = self.provider.model_name(self.config)

        # Adjust parameters based on analysis depth
        analysis_depth = self.config.analysis_depth
        if analysis_depth == 'quick':
            max_tokens = 4000
            temperature = 0.2
        elif analysis_depth == 'detailed':
            max_tokens = 12000
            temperature = 0.05
        else:  # standard
            max_tokens = 8000
            temperature = 0.1

        # Choose system message based on analysis style
        analysis_style = getattr(self.config, 'analysis_style', 'severity')

        # Load system prompt from file
        system_content = self.load_system_prompt(analysis_style)

        # Retry configuration
        max_retries = int(os.environ.get('API_MAX_RETRIES', '3'))
        timeout_seconds = int(os.environ.get('API_TIMEOUT_SECONDS', '120'))

        last_error = None

        for attempt in range(max_retries):
            try:
                print(f"Calling AI API (attempt {attempt + 1}/{max_retries})...")

                return self.provider.complete(
                    self.ai_client, model_name, system_content, scrubbed_prompt,
                    temperature, max_tokens, timeout_seconds
                )

            except Exception as e:
                last_error = e
                error_type = type(e).__name__
                
                # Sanitize error message to avoid leaking credentials
                safe_error = self._sanitize_error_message(str(e))
                
                if attempt < max_retries - 1:
                    # Exponential backoff: 2^attempt seconds
                    wait_time = 2 ** attempt
                    print(f"Warning: AI API error ({error_type}): {safe_error}", file=sys.stderr)
                    print(f"Retrying in {wait_time} seconds...", file=sys.stderr)
                    time.sleep(wait_time)
                else:
                    # Final attempt failed
                    print(f"Error: AI API failed after {max_retries} attempts: {safe_error}", file=sys.stderr)
        
        # All retries failed
        safe_error = self._sanitize_error_message(str(last_error))
        error_msg = f"## Analysis Error\n\n**AI API Error:** {safe_error}\n\n"
        error_msg += f"**Attempts:** {max_retries}\n"
        error_msg += f"**Provider:** {self.config.ai_provider}\n\n"
        error_msg += "Please check your AI provider configuration and try again.\n\n"
        error_msg += "**Troubleshooting:**\n"
        error_msg += "- Verify your API credentials are correct\n"
        error_msg += "- Check API quota and rate limits\n"
        error_msg += "- Ensure network connectivity to AI service\n"
        
        return error_msg
    
    def _sanitize_error_message(self, error_msg: str) -> str:
        """Remove sensitive information from error messages
        
        Args:
            error_msg: Raw error message that may contain sensitive data
            
        Returns:
            Sanitized error message safe for logging/display
        """
        sanitized = error_msg
        
        # Remove API keys (various formats)
        if self.config.azure_openai_api_key:
            sanitized = sanitized.replace(self.config.azure_openai_api_key, '***REDACTED***')
        
        # Remove endpoints/URLs (may contain sensitive paths)
        if self.config.azure_openai_endpoint:
            sanitized = sanitized.replace(self.config.azure_openai_endpoint, '***REDACTED_ENDPOINT***')
        
        # Remove file paths that may contain sensitive directory names
        sanitized = re.sub(r'/[a-zA-Z0-9/_-]+/terraform', '***/terraform', sanitized)
        sanitized = re.sub(r'C:\\[a-zA-Z0-9\\_-]+\\terraform', '***\\terraform', sanitized)
        
        # Remove any remaining patterns that look like API keys (alphanumeric 32+ chars)
        sanitized = re.sub(r'\b[A-Za-z0-9]{32,}\b', '***REDACTED***', sanitized)
        
        return sanitized
    
    def run_analysis(self) -> Dict[str, Any]:
        """Run the complete analysis"""
        print("Starting Terraform AI analysis...")
        
        # Load Terraform plan
        try:
            with open(self.config.terraform_plan_path, 'r') as f:
                plan_data = json.load(f)
        except Exception as e:
            error_msg = f"Error loading Terraform plan: {e}"
            print(error_msg, file=sys.stderr)
            return {"error": error_msg}
        
        # Read Terraform files (unless in plan-only mode)
        if self.config.analysis_mode == "comprehensive":
            print("Reading Terraform configuration files...")
        all_tf_files, changed_tf_files = self.read_terraform_files()
        
        # Detect cloud providers
        print("Detecting providers...")
        providers = CloudProviderDetector.detect_providers(all_tf_files, plan_data)
        
        # Format plan changes
        print("Analysing plan changes...")
        plan_changes, resource_types, action_counts = self.format_plan_changes(plan_data)
        
        # Get MCP insights if available
        mcp_results = {}
        if self.mcp_client:
            print("Getting insights from Terraform MCP server...")
            mcp_results = self.mcp_client.validate_plan_with_mcp(plan_data)
            mcp_status = mcp_results.get("mcp_status", "unknown")
            if mcp_status == "connected":
                print("Connected to HashiCorp MCP server via stdio protocol")

            elif mcp_status == "unavailable":
                print("Note: MCP server not available, continuing without MCP validation")
            elif mcp_status == "failed":
                print("Error: MCP server connection failed")
            else:
                print(f"MCP server status: {mcp_status}")
        
        # Create analysis prompt with MCP insights
        prompt = self.create_analysis_prompt(
            all_tf_files, changed_tf_files, plan_changes, 
            resource_types, action_counts, providers,
            mcp_insights=mcp_results  # Pass MCP insights to enhance AI analysis
        )
        
        # Analyse with AI
        print("Analysing with AI...")
        ai_analysis = self.analyse_with_ai(prompt)
        
        # Combine results
        final_analysis = f"## Terraform AI Plan Analysis\n\n"
        final_analysis += f"**Analysis Mode:** {self.config.analysis_mode.title()}\n"
        final_analysis += f"**Providers Detected:** {', '.join(providers) if providers else 'Unknown'}\n"
        final_analysis += f"**Analysis Focus:** {', '.join(self.config.analysis_focus)}\n\n"
        final_analysis += ai_analysis
        
        # Add MCP validation results if available and show_mcp_details flag is enabled
        if self.config.show_mcp_details and (mcp_results.get("validation_results") or mcp_results.get("provider_insights")):
            final_analysis += "\n\n## HashiCorp MCP Server Analysis\n\n"
            final_analysis += "_This section provides detailed MCP server diagnostics for troubleshooting._\n\n"
            
            # Connection status
            mcp_status = mcp_results.get("mcp_status", "unknown")
            status_emoji = {
                "connected": "✅",
                "failed": "❌",
                "unavailable": "⚠️"
            }.get(mcp_status, "❓")
            final_analysis += f"**Connection Status:** {status_emoji} {mcp_status.replace('_', ' ').title()}\n\n"
            
            # Enhanced provider insights with version info
            provider_insights = mcp_results.get("provider_insights", {})
            version_info = mcp_results.get("version_compatibility", {})
            
            if provider_insights or version_info:
                final_analysis += "### Provider Documentation & Version Status\n"
                for provider in set(list(provider_insights.keys()) + list(version_info.keys())):
                    insights = provider_insights.get(provider, {})
                    version = version_info.get(provider, {})
                    
                    status = insights.get("status", "unknown")
                    doc_count = insights.get("doc_count", 0)
                    latest_version = version.get("latest_version", "unknown")
                    registry_url = version.get("registry_url", "")
                    
                    if status == "available":
                        version_link = f" | [Registry]({registry_url})" if registry_url else ""
                        final_analysis += f"- **{provider.upper()}**: ✅ {doc_count} resources documented | Latest: v{latest_version}{version_link}\n"
                    elif status == "limited":
                        final_analysis += f"- **{provider.upper()}**: ⚠️ Limited documentation available | Latest: v{latest_version}\n"
                    else:
                        final_analysis += f"- **{provider.upper()}**: ❌ Documentation unavailable | Latest: v{latest_version}\n"
                final_analysis += "\n"
            
            # Resource-specific documentation
            resource_docs = mcp_results.get("resource_documentation", {})
            if resource_docs:
                final_analysis += "### Resource-Specific Documentation\n"
                for resource_type, doc_info in resource_docs.items():
                    status = doc_info.get("status", "unknown")
                    if status == "available":
                        doc_url = doc_info.get("url", "")
                        url_link = f" | [Documentation]({doc_url})" if doc_url else ""
                        final_analysis += f"- **`{resource_type}`**: ✅ Detailed documentation available{url_link}\n"
                    elif status == "found_search_only":
                        final_analysis += f"- **`{resource_type}`**: ⚠️ Basic documentation found\n"
                    else:
                        final_analysis += f"- **`{resource_type}`**: ❌ Documentation unavailable\n"
                final_analysis += "\n"
            
            # Validation results
            validation_results = mcp_results.get("validation_results", [])
            if validation_results:
                final_analysis += "### Validation Results\n"
                for result in validation_results:
                    status = result.get('status', 'unknown')
                    emoji = "✅" if status == "pass" else "❌" if status == "fail" else "⚠️"
                    final_analysis += f"{emoji} **{result.get('rule', 'Unknown Rule')}**: {result.get('message', 'No message')}\n"
                final_analysis += "\n"
            
            # Module suggestions with links
            module_suggestions = mcp_results.get("module_suggestions", [])
            if module_suggestions:
                final_analysis += "### Recommended Modules\n"
                for suggestion in module_suggestions:
                    provider = suggestion.get("provider", "")
                    modules = suggestion.get("modules", [])
                    total = suggestion.get("total_found", 0)
                    
                    if modules:
                        final_analysis += f"**{provider.upper()} Provider** ({total} modules found):\n"
                        for module in modules:
                            name = module.get("name", "")
                            description = module.get("description", "")
                            # Create registry link for modules
                            module_url = f"https://registry.terraform.io/modules/{name}" if "/" in name else ""
                            url_link = f" | [Registry]({module_url})" if module_url else ""
                            final_analysis += f"- [`{name}`]({module_url}): {description}{url_link}\n"
                        final_analysis += "\n"
            
            # MCP recommendations
            mcp_recommendations = mcp_results.get("recommendations", [])
            if mcp_recommendations:
                final_analysis += "### MCP Server Recommendations\n"
                for rec in mcp_recommendations:
                    final_analysis += f"- {rec}\n"
        
        # Create summary
        has_critical_issues = any(word in ai_analysis.lower() for word in [
            'critical', 'security risk', 'vulnerability', 'exposed', 'dangerous', 'insecure'
        ])
        
        recommendations_count = ai_analysis.lower().count('recommend') + ai_analysis.lower().count('suggest')
        
        summary = {
            "has_critical_issues": has_critical_issues,
            "recommendations_count": recommendations_count,
            "providers_detected": providers,
            "resource_changes": len(plan_changes),
            "action_counts": action_counts,
            "mcp_status": mcp_results.get("mcp_status", "unknown"),
            "mcp_validations": len(mcp_results.get("validation_results", [])),
            "mcp_insights": len(mcp_results.get("provider_insights", {})),
            "mcp_modules": len(mcp_results.get("module_suggestions", [])),
            "mcp_resource_docs": len(mcp_results.get("resource_documentation", {})),
            "mcp_version_checks": len(mcp_results.get("version_compatibility", {}))
        }
        
        # Save results
        with open('ai_analysis.md', 'w') as f:
            f.write(final_analysis)
        
        with open('analysis_summary.json', 'w') as f:
            json.dump(summary, f, indent=2)
        
        print("Analysis completed successfully!")
        return {"analysis": final_analysis, "summary": summary}


def load_config_from_env() -> AnalysisConfig:
    """Load configuration from environment variables"""
    ai_provider = os.environ.get("AI_PROVIDER", "azure").lower()

    # Validate AI provider and required credentials
    if ai_provider not in PROVIDERS:
        print(f"ERROR: Unsupported AI provider '{ai_provider}'. Must be one of: {', '.join(PROVIDERS.keys())}", file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("AZURE_OPENAI_API_KEY"):
        print("ERROR: AZURE_OPENAI_API_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)
    if not os.environ.get("AZURE_OPENAI_ENDPOINT"):
        print("ERROR: AZURE_OPENAI_ENDPOINT environment variable is required", file=sys.stderr)
        sys.exit(1)
    
    # Check if terraform plan exists
    terraform_plan_path = os.environ.get("TERRAFORM_PLAN_PATH", "tfplan.json")
    if not os.path.exists(terraform_plan_path):
        print(f"ERROR: Terraform plan not found at: {terraform_plan_path}", file=sys.stderr)
        print("Please ensure terraform plan has been run and the JSON output is available.", file=sys.stderr)
        sys.exit(1)
    
    # Resolve analysis focus from preset or use explicit focus
    analysis_focus = resolve_analysis_preset(
        os.environ.get("ANALYSIS_PRESET", ""),
        os.environ.get("ANALYSIS_FOCUS", "security,cost,best-practices,deployment")
    )
    
    return AnalysisConfig(
        ai_provider=ai_provider,
        azure_openai_api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
        azure_openai_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        azure_openai_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini"),
        terraform_plan_path=terraform_plan_path,
        terraform_directory=os.environ.get("TERRAFORM_DIRECTORY", "."),
        analysis_focus=analysis_focus.split(","),
        analysis_mode=os.environ.get("ANALYSIS_MODE", "comprehensive"),
        analysis_style=os.environ.get("ANALYSIS_STYLE", "severity"),
        analysis_depth=os.environ.get("ANALYSIS_DEPTH", "standard"),
        mcp_available=os.environ.get("MCP_AVAILABLE", "false").lower() == "true",
        skip_mcp=os.environ.get("SKIP_MCP", "false").lower() == "true",
        show_mcp_details=os.environ.get("SHOW_MCP_DETAILS", "false").lower() == "true"
    )


def resolve_analysis_preset(preset: str, explicit_focus: str) -> str:
    """Resolve analysis preset to focus areas
    
    Args:
        preset: Preset name (security-audit, cost-optimisation, production-ready, quick-check, complete)
        explicit_focus: Explicit focus areas (used if preset is empty)
    
    Returns:
        Comma-separated focus areas
    """
    presets = {
        "security-audit": "security,compliance,governance",
        "cost-optimisation": "cost,performance,data",
        "production-ready": "security,reliability,deployment,observability,performance",
        "quick-check": "security,best-practices",
        "complete": "security,cost,best-practices,deployment,compliance,performance,reliability,observability,networking,data,governance"
    }
    
    if preset and preset in presets:
        print(f"Using analysis preset: {preset} -> {presets[preset]}")
        return presets[preset]
    elif preset:
        print(f"Warning: Unknown preset '{preset}', using explicit focus areas", file=sys.stderr)
        return explicit_focus
    else:
        return explicit_focus




def main():
    """Main entry point"""
    try:
        config = load_config_from_env()
        analyser = TerraformAnalyser(config)
        result = analyser.run_analysis()
        
        if "error" in result:
            print(f"ERROR: Analysis failed: {result['error']}")
            sys.exit(1)
        
    except KeyError as e:
        print(f"ERROR: Missing required environment variable: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()