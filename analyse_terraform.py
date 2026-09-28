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


MCP_IMAGE = "hashicorp/terraform-mcp-server@sha256:423a6b8e2ee06affcf090892f40c86469caba45fd2448ffa8ca5d717a174f7d5"


@dataclass
class AnalysisConfig:
    """Configuration for a Foundry-backed Terraform review."""
    ai_provider: str = "foundry-openai"
    foundry_api_key: Optional[str] = None
    foundry_endpoint: Optional[str] = None
    foundry_deployment: Optional[str] = None
    terraform_plan_path: str = "tfplan.json"
    terraform_directory: str = "."
    analysis_focus: Optional[List[str]] = None
    analysis_preset: str = ""
    analysis_mode: str = "plan-only"
    analysis_depth: str = "detailed"
    analysis_style: str = "severity"
    fail_on_severity: str = "none"
    mcp_available: bool = False
    skip_mcp: bool = False
    max_prompt_chars: int = 120000
    target_prompt_chars: int = 100000
    max_resources_per_request: int = 100

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
                MCP_IMAGE
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
    
    async def _get_resource_specific_docs(self, plan_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch bounded, genuine documentation for resource types in the plan."""
        resource_docs = {}
        resource_types = sorted({
            change.get("type", "")
            for change in plan_data.get("resource_changes", [])
            if change.get("type")
        })[:5]
        for resource_type in resource_types:
            try:
                provider_name, _, service_slug = resource_type.partition("_")
                registry_provider = {"azure": "azurerm", "gcp": "google"}.get(
                    provider_name, provider_name
                )
                search_response = await self._send_mcp_request("tools/call", {
                    "name": "search_providers",
                    "arguments": {
                        "provider_name": registry_provider,
                        "provider_namespace": "hashicorp",
                        "service_slug": service_slug or resource_type,
                        "provider_data_type": "resources",
                    },
                })
                if not search_response or "result" not in search_response:
                    resource_docs[resource_type] = {
                        "status": "error", "error": f"Documentation search failed for {resource_type}"
                    }
                    continue
                content = search_response["result"].get("content", [])
                text = content[0].get("text", "") if content and isinstance(content[0], dict) else ""
                if not text:
                    resource_docs[resource_type] = {
                        "status": "error", "error": f"Empty documentation response for {resource_type}"
                    }
                    continue
                doc_ids = re.findall(r'providerDocID:\s*(\w+)', text)
                if not doc_ids:
                    resource_docs[resource_type] = {
                        "status": "found_search_only", "search_result": text[:300]
                    }
                    continue
                doc_response = await self._send_mcp_request("tools/call", {
                    "name": "get_provider_details",
                    "arguments": {"provider_doc_id": doc_ids[0]},
                })
                if not doc_response or "result" not in doc_response:
                    resource_docs[resource_type] = {
                        "status": "error", "error": f"Documentation detail lookup failed for {resource_type}"
                    }
                    continue
                doc_content = doc_response["result"].get("content", [])
                doc_text = doc_content[0].get("text", "") if doc_content and isinstance(doc_content[0], dict) else ""
                if not doc_text:
                    resource_docs[resource_type] = {
                        "status": "error", "error": f"Empty documentation detail for {resource_type}"
                    }
                    continue
                url_match = re.search(r'https://registry\.terraform\.io/providers/[^\s]+', doc_text)
                resource_docs[resource_type] = {
                    "documentation": doc_text[:1000],
                    "url": url_match.group(0) if url_match else None,
                    "status": "available",
                }
            except Exception as exc:
                safe_error = str(exc) or type(exc).__name__
                print(f"Warning: Could not get docs for {resource_type}: {safe_error}", file=sys.stderr)
                resource_docs[resource_type] = {"status": "error", "error": safe_error}
        return resource_docs

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
        """Return genuine registry documentation when available, never fail review."""
        if not self.available:
            return {"status": "unavailable", "documents": [], "errors": ["Docker unavailable"]}
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._validate_plan_async(plan_data))
            finally:
                loop.close()
        except Exception as exc:
            safe_error = str(exc) or type(exc).__name__
            print(f"Warning: MCP validation failed: {safe_error}", file=sys.stderr)
            return {"status": "unavailable", "documents": [], "errors": [safe_error]}

    async def _validate_plan_async(self, plan_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch bounded resource documentation over MCP stdio."""
        try:
            if not await self._initialize_mcp():
                return {"status": "unavailable", "documents": [], "errors": ["MCP initialization failed"]}
            resource_docs = await self._get_resource_specific_docs(plan_data)
            documents = []
            errors = []
            for resource_type, info in sorted(resource_docs.items()):
                if info.get("status") in {"available", "found_search_only"}:
                    documents.append({
                        "resource_type": resource_type,
                        "url": info.get("url", ""),
                        "excerpt": str(info.get("documentation") or info.get("search_result") or "")[:500],
                    })
                elif info.get("status") == "error":
                    errors.append(str(info.get("error") or f"Lookup failed for {resource_type}"))
            status = "available" if documents or not errors else "unavailable"
            return {"status": status, "documents": documents, "errors": errors}
        except Exception as exc:
            safe_error = str(exc) or type(exc).__name__
            print(f"Warning: MCP documentation lookup failed: {safe_error}", file=sys.stderr)
            return {"status": "unavailable", "documents": [], "errors": [safe_error]}
        finally:
            await self._cleanup_mcp()

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


# -- Scrubbed, change-level Terraform evidence -------------------------------
#
# These helpers turn a raw `resource_changes[]` entry from `terraform show -json`
# into bounded, deterministic evidence for the AI prompt: sensitive values are
# redacted, planned-but-unknown values are masked, and only fields that actually
# changed are surfaced. They never send raw sensitive/unknown values downstream.

SENSITIVE_MASK = "<redacted-sensitive>"
UNKNOWN_MASK = "<unknown-until-apply>"


def _mask_marked_values(value: Any, marks: Any, replacement: str) -> Any:
    """Recursively replace parts of `value` flagged by `marks` with `replacement`.

    `marks` mirrors Terraform's `before_sensitive`/`after_sensitive`/`after_unknown`
    shape: `True` marks the whole subtree, dicts/lists mirror `value`'s structure to
    mark nested fields, and anything else (None, False, missing) leaves `value` as-is.
    """
    if marks is True:
        return replacement
    if isinstance(marks, dict) and isinstance(value, dict):
        return {
            key: _mask_marked_values(item, marks.get(key), replacement)
            for key, item in value.items()
        }
    if isinstance(marks, list) and isinstance(value, list):
        return [
            _mask_marked_values(item, marks[index] if index < len(marks) else None, replacement)
            for index, item in enumerate(value)
        ]
    return value


def _mark_unknown_values(value: Any, marks: Any) -> Any:
    """Replace planned values Terraform cannot know until apply with `UNKNOWN_MASK`."""
    return _mask_marked_values(value, marks, UNKNOWN_MASK)


def _changed_paths(before: Any, after: Any, prefix: str = "") -> List[str]:
    """Return dotted/bracketed paths for every leaf that differs between before/after.

    Examples: `allocated_storage`, `network_interface[0].private_ip`.
    """
    if isinstance(before, dict) or isinstance(after, dict):
        before_dict = before if isinstance(before, dict) else {}
        after_dict = after if isinstance(after, dict) else {}
        paths = []
        for key in sorted(set(before_dict) | set(after_dict)):
            child_prefix = f"{prefix}.{key}" if prefix else key
            paths.extend(_changed_paths(before_dict.get(key), after_dict.get(key), child_prefix))
        return paths

    if isinstance(before, list) or isinstance(after, list):
        before_list = before if isinstance(before, list) else []
        after_list = after if isinstance(after, list) else []
        paths = []
        for index in range(max(len(before_list), len(after_list))):
            before_item = before_list[index] if index < len(before_list) else None
            after_item = after_list[index] if index < len(after_list) else None
            paths.extend(_changed_paths(before_item, after_item, f"{prefix}[{index}]"))
        return paths

    if before != after:
        return [prefix] if prefix else []
    return []


def _marked_paths(marks: Any, prefix: str = "") -> List[str]:
    """Return dotted/bracketed leaf paths where `marks` is True.

    Used for `after_unknown`: a field can be marked unknown while its raw before/after
    values are otherwise indistinguishable (e.g. both `None`), so this must be unioned
    into `_changed_paths` rather than relying on a raw value diff alone.
    """
    if marks is True:
        return [prefix] if prefix else []
    if isinstance(marks, dict):
        paths = []
        for key, sub_marks in marks.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            paths.extend(_marked_paths(sub_marks, child_prefix))
        return paths
    if isinstance(marks, list):
        paths = []
        for index, sub_marks in enumerate(marks):
            paths.extend(_marked_paths(sub_marks, f"{prefix}[{index}]"))
        return paths
    return []


def _top_level_field(path: str) -> str:
    """Extract the top-level field name from a changed path, e.g. `network_interface`
    from `network_interface[0].private_ip`."""
    for index, char in enumerate(path):
        if char in ".[":
            return path[:index]
    return path


def _only_changed_fields(value: Any, fields: set) -> Any:
    """Reduce a dict to only the top-level keys that actually changed."""
    if not isinstance(value, dict):
        return value
    return {key: item for key, item in value.items() if key in fields}


def normalise_plan_change(change: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalise one Terraform `resource_changes[]` entry into scrubbed evidence.

    Sensitive values are replaced with `SENSITIVE_MASK` and values Terraform cannot
    know until apply are replaced with `UNKNOWN_MASK`. `delete`+`create` collapses to
    a single `replace` action. No-op changes return `None` so callers can filter them
    out before building bounded prompt evidence.

    Returns a dict with `address`, `resource_type`, `action`, `changed_paths`,
    `before`, and `after` (the latter two reduced to only the fields that changed).
    """
    details = change.get("change") or {}
    actions = details.get("actions") or ["no-op"]

    if set(actions) == {"delete", "create"}:
        action = "replace"
    else:
        action = actions[0] if actions else "no-op"

    if action == "no-op":
        return None

    raw_before = details.get("before")
    raw_after = details.get("after")
    # A field can be marked unknown-until-apply while its raw before/after values are
    # otherwise indistinguishable (e.g. both None), so union in paths from after_unknown.
    changed_paths = sorted(set(_changed_paths(raw_before, raw_after)) | set(_marked_paths(details.get("after_unknown"))))
    changed_fields = {_top_level_field(path) for path in changed_paths}

    masked_before = _mask_marked_values(raw_before, details.get("before_sensitive"), SENSITIVE_MASK)
    masked_after = _mask_marked_values(raw_after, details.get("after_sensitive"), SENSITIVE_MASK)
    masked_after = _mark_unknown_values(masked_after, details.get("after_unknown"))

    return {
        "address": change.get("address", "unknown"),
        "resource_type": change.get("type", "unknown"),
        "action": action,
        "changed_paths": changed_paths,
        "before": _only_changed_fields(masked_before, changed_fields),
        "after": _only_changed_fields(masked_after, changed_fields),
    }


def summarise_report(markdown: str, mcp_status: str = "unknown") -> Dict[str, Any]:
    """Extract deterministic automation metadata from report sections."""
    sections = {}
    current = None
    for line in markdown.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        numbered_heading = re.match(r"^\s*\d+\.\s+\*\*(.+?)\*\*\s*$", line)
        matched_heading = heading or numbered_heading
        if matched_heading:
            current = re.sub(
                r"\s*\([^)]*\)\s*$", "", matched_heading.group(1)
            ).strip().lower()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    def has_content(name: str) -> bool:
        empty_values = {
            "none", "none identified", "no findings", "no issues",
            "no critical issues", "no warnings", "n/a", "not applicable",
        }
        for line in sections.get(name, []):
            value = re.sub(r"^\s*(?:[-*+]\s+|#{3,6}\s+)", "", line).strip()
            value = re.sub(r"[.*_`]+", "", value).strip().rstrip(".").lower()
            if value and value not in empty_values and not value.startswith("no "):
                return True
        return False

    finding_lines = [
        line.strip()
        for name, lines in sections.items()
        if name not in {"summary", "quick reference table", "immediate actions"}
        for line in lines
        if re.match(r"^\s*(?:[-*+]\s+|#{3,6}\s+)", line)
    ]
    domain_has_critical = any(re.search(r"🔴\s*(?:critical)?", line, re.IGNORECASE) for line in finding_lines)
    domain_has_warning = any(re.search(r"🟡\s*(?:warning)?", line, re.IGNORECASE) for line in finding_lines)

    if has_content("critical issues") or domain_has_critical:
        highest = "critical"
    elif has_content("warnings") or domain_has_warning:
        highest = "warning"
    else:
        highest = "none"
    recommendation_lines = [
        line for line in sections.get("recommendations", [])
        if re.match(r"^\s*[-*+]\s+", line)
    ]
    recommendation_lines.extend(
        line.strip()
        for name, lines in sections.items()
        if name != "recommendations"
        for line in lines
        if re.match(r"^\s*[-*+]\s+", line)
        and re.search(r"🔵\s*(?:recommendation)?", line, re.IGNORECASE)
    )
    return {
        "highest_severity": highest,
        "has_issues": highest != "none",
        "has_critical_issues": highest == "critical",
        "recommendations_count": len(recommendation_lines),
        "mcp_status": mcp_status,
    }


def severity_gate(summary: Dict[str, Any], threshold: str) -> bool:
    """Return whether a completed report meets the configured failure threshold."""
    if threshold == "none":
        return False
    if threshold == "warning":
        return summary.get("highest_severity") in {"warning", "critical"}
    if threshold == "critical":
        return summary.get("highest_severity") == "critical"
    raise ValueError("fail-on-severity must be one of: none, warning, critical")



class TerraformAnalyser:
    """Main Terraform analysis class"""
    
    def __init__(self, config: AnalysisConfig):
        self.config = config
        self._validate_inputs()  # Validate all inputs before processing
        self.mcp_client = TerraformMCPClient() if not config.skip_mcp else None
        self.openai_client = self._init_openai_client()
    
    def _init_openai_client(self):
        """Initialize the Microsoft Foundry OpenAI-compatible client."""
        from openai import OpenAI
        return OpenAI(
            api_key=self.config.foundry_api_key,
            base_url=f"{self.config.foundry_endpoint.rstrip('/')}/openai/v1/",
            # Retry ownership belongs to analyse_with_ai.  Leaving the SDK default
            # enabled silently multiplies a configured timeout and makes a single
            # action attempt take several minutes.
            max_retries=0,
        )

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
            abs_path = os.path.realpath(path)
        else:
            abs_path = os.path.realpath(os.path.join(base_dir, path))
        
        abs_base = os.path.realpath(base_dir)
        
        # Ensure path is within base directory
        if not abs_path.startswith(abs_base + os.sep) and abs_path != abs_base:
            raise ValueError(
                f"Security Error: Path '{path}' attempts to access files outside allowed directory. "
                f"Allowed: {abs_base}, Requested: {abs_path}"
            )
        
        return abs_path
    
    def _validate_inputs(self) -> None:
        """Validate all configuration inputs to prevent injection attacks"""
        
        if self.config.ai_provider != 'foundry-openai':
            raise ValueError("ai-provider must be foundry-openai")
        if not self.config.foundry_api_key:
            raise ValueError("Foundry API key is required")
        if not self.config.foundry_endpoint:
            raise ValueError("Foundry endpoint is required")
        from urllib.parse import urlparse
        endpoint = urlparse(self.config.foundry_endpoint)
        if endpoint.scheme != 'https' or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
            raise ValueError("Foundry endpoint must be an HTTPS URL without credentials, query, or fragment")
        if not self.config.foundry_deployment:
            raise ValueError("Foundry deployment is required")
        if self.config.max_prompt_chars < 1000:
            raise ValueError("max-prompt-chars must be at least 1000")
        if not 1000 <= self.config.target_prompt_chars <= self.config.max_prompt_chars:
            raise ValueError("target-prompt-chars must be between 1000 and max-prompt-chars")
        if self.config.max_resources_per_request < 1:
            raise ValueError("max-resources-per-request must be at least 1")

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
    
    def read_terraform_files(self) -> Dict[str, str]:
        """Read all Terraform files under terraform_directory with size limits, in sorted
        (deterministic) order"""
        all_tf_files = {}

        # Skip file reading in plan-only mode
        if self.config.analysis_mode == "plan-only":
            print("Plan-only mode: Skipping Terraform file reading")
            return all_tf_files

        # File size limits (configurable via environment; defaults match action.yml)
        max_file_size = int(os.environ.get('MAX_FILE_SIZE_MB', '10')) * 1_000_000  # Default 10MB per file
        max_total_size = int(os.environ.get('MAX_TOTAL_SIZE_MB', '50')) * 1_000_000  # Default 50MB total
        max_files = int(os.environ.get('MAX_FILES', '100'))  # Default 100 files

        total_size = 0
        file_count = 0

        # Read all .tf files in the specified directory (already validated), in
        # sorted order so the included file set is deterministic
        tf_pattern = os.path.join(self.config.terraform_directory, "**/*.tf")

        for tf_file in sorted(glob.glob(tf_pattern, recursive=True)):
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
                    rel_path = os.path.relpath(
                        validated_path, os.path.realpath(self.config.terraform_directory)
                    )
                    all_tf_files[rel_path] = f.read()
                    total_size += file_size
                    file_count += 1
            except Exception as e:
                print(f"Warning: Could not read {tf_file}: {e}", file=sys.stderr)
        
        print(f"Read {file_count} Terraform files ({total_size} bytes total)")

        return all_tf_files
    
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
        """Create the analysis prompt for OpenAI with optional MCP insights integration and data scrubbing

        `plan_changes` is expected to be a list of changes already normalised by
        `normalise_plan_change` (scrubbed of sensitive/unknown values, reduced to
        changed fields only). `changed_files` is accepted for signature
        compatibility but is no longer used: comprehensive mode always sources
        evidence from `tf_files` (the full, sorted Terraform configuration).
        """

        primary_provider = CloudProviderDetector.get_primary_provider(providers)
        provider_context = f"**Detected Providers:** {', '.join(providers) if providers else 'Unknown (plan-only mode)'}\n"
        provider_context += f"**Primary Provider:** {primary_provider.upper()}\n\n"

        # Determine context based on analysis mode and available data
        if self.config.analysis_mode == "plan-only":
            context_description = "This analysis focuses on reviewing the Terraform plan JSON output only. Source files were not analysed for faster execution."
            tf_context = "### Analysis Mode: Plan-Only\n\n"
            tf_context += "**Note:** This analysis is based solely on the Terraform plan JSON. For more comprehensive analysis including source file review, use 'comprehensive' mode.\n\n"
        else:
            context_description = "This comprehensive analysis reviews both the Terraform plan and the overall configuration."
            tf_context = "### Terraform Configuration:\n\n"
            for filepath, content in sorted(tf_files.items()):
                scrubbed_content = self._scrub_sensitive_data(content)
                tf_context += f"**{filepath}:**\n```hcl\n{scrubbed_content}\n```\n\n"

        # Format plan changes
        plan_summary = f"### Plan Summary:\n"
        plan_summary += f"- **Create:** {action_counts['create']} resources\n"
        plan_summary += f"- **Update:** {action_counts['update']} resources\n"
        plan_summary += f"- **Delete:** {action_counts['delete']} resources\n"
        plan_summary += f"- **Replace:** {action_counts['replace']} resources\n\n"

        plan_text = "### Detailed Plan Changes:\n\n"
        plan_text += "Evidence limits: only included changes and source files may support findings\n\n"
        if not plan_changes:
            plan_text += "No resource changes detected in the plan.\n\n"
        else:
            for change in plan_changes:
                plan_text += f"**Action:** {change['action']}\n"
                plan_text += f"**Resource:** {change['address']}\n"
                changed_fields = ", ".join(f"`{path}`" for path in change['changed_paths'])
                plan_text += f"**Changed fields:** {changed_fields}\n"
                evidence = {"before": change['before'], "after": change['after']}
                plan_text += f"```json\n{json.dumps(evidence, sort_keys=True)}\n```\n"
                plan_text += "\n---\n\n"
        
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
        
        # MCP content is untrusted reference data and never an instruction source.
        mcp_context = ""
        if mcp_insights and mcp_insights.get("status") == "available":
            documents = mcp_insights.get("documents", [])
            if documents:
                mcp_context = "\n### Terraform Registry Documentation (untrusted reference data)\n\n"
                for document in documents:
                    resource_type = document.get("resource_type", "unknown")
                    excerpt = str(document.get("excerpt", ""))[:500]
                    url = document.get("url", "")
                    mcp_context += f"- `{resource_type}`: {excerpt}"
                    if url:
                        mcp_context += f" ([Docs]({url}))"
                    mcp_context += "\n"
                mcp_context += "\n"

        # Determine analysis depth instructions
        analysis_depth = getattr(self.config, 'analysis_depth', 'standard')
        depth_instruction = ""
        if analysis_depth == 'quick':
            depth_instruction = "Provide a focused analysis highlighting the most critical issues and essential recommendations. Be concise but thorough on high-impact items."
        elif analysis_depth == 'detailed':
            depth_instruction = "Provide an exhaustive analysis with detailed explanations, comprehensive recommendations, and extensive context for each finding. Include learning opportunities and advanced optimisation suggestions."
        else:  # standard
            depth_instruction = "Provide a balanced analysis covering all significant issues with practical recommendations and clear explanations."

        if self.config.analysis_style == "domain":
            output_structure = """Use `## Summary`, then `## Quick Reference Table`, followed by level-two headings for each requested analysis domain. Start every finding with 🔴 Critical, 🟡 Warning, 🔵 Recommendation, or ✅ Good Practice. End with `## Immediate actions`."""
        else:
            output_structure = """Use these exact level-two headings:
- `## Summary`
- `## Quick Reference Table`
- `## Critical Issues (🔴)`
- `## Warnings (🟡)`
- `## Recommendations (🔵)`
- `## Good Practices (✅)`
- `## Immediate actions`"""

        return f"""
You are a senior DevOps and cloud infrastructure expert with extensive experience in Terraform, cloud security, and infrastructure best practices. {context_description}

{provider_context}

**Analysis Scope:**
{focus_text}

{provider_guidance}

{mcp_context}

**Review depth instruction:** {depth_instruction}

## ANALYSIS METHODOLOGY
1. **Security Assessment**: Identify vulnerabilities, exposed resources, misconfigurations
2. **Risk Evaluation**: Assess deployment risks, breaking changes, data loss potential
3. **Optimisation Review**: Find cost savings, performance improvements, best practices
4. **Compliance Check**: Verify adherence to standards and policies
5. **Operational Readiness**: Evaluate monitoring, logging, backup, disaster recovery

## INFRASTRUCTURE DATA

{tf_context}

{plan_summary}

{plan_text}

**Resource Types:** {', '.join(resource_types) if resource_types else 'None'}

## OUTPUT REQUIREMENTS
{output_structure}

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

    def build_prompt_batches(self, tf_files: Dict[str, str], plan_changes: List[Dict],
                             resource_types: List[str], action_counts: Dict[str, int],
                             providers: List[str], mcp_insights: Dict[str, Any]) -> List[str]:
        """Pack all accepted resource evidence without exceeding public limits."""
        batches: List[str] = []
        current: List[Dict] = []
        for change in plan_changes:
            candidate = current + [change]
            candidate_prompt = self.create_analysis_prompt(tf_files, {}, candidate, resource_types, action_counts, providers, mcp_insights)
            if len(candidate) <= self.config.max_resources_per_request and len(candidate_prompt) <= self.config.target_prompt_chars:
                current = candidate
                continue
            if not current:
                if len(candidate_prompt) > self.config.max_prompt_chars:
                    raise RuntimeError(f"A single resource evidence item exceeds max-prompt-chars ({self.config.max_prompt_chars})")
                current = candidate
                continue
            batches.append(self.create_analysis_prompt(tf_files, {}, current, resource_types, action_counts, providers, mcp_insights))
            current = [change]
            if len(self.create_analysis_prompt(tf_files, {}, current, resource_types, action_counts, providers, mcp_insights)) > self.config.max_prompt_chars:
                raise RuntimeError(f"A single resource evidence item exceeds max-prompt-chars ({self.config.max_prompt_chars})")
        if current or not batches:
            batches.append(self.create_analysis_prompt(tf_files, {}, current, resource_types, action_counts, providers, mcp_insights))
        if any(len(prompt) > self.config.max_prompt_chars for prompt in batches):
            raise RuntimeError("A packed review request exceeded max-prompt-chars")
        return batches
    
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
    
    def analyse_with_ai(self, prompt: str, max_completion_tokens: Optional[int] = None) -> str:
        """Analyse the Terraform plan using Microsoft Foundry with retry logic."""
        # Scrub sensitive data from prompt before sending to AI
        scrubbed_prompt = self._scrub_sensitive_data(prompt)
        
        # Validate prompt size to avoid token limits
        prompt_length = len(scrubbed_prompt)
        if prompt_length > self.config.max_prompt_chars:
            raise RuntimeError(
                f"Serialized review prompt is {prompt_length} characters, above max-prompt-chars "
                f"({self.config.max_prompt_chars}). The review was not sent, so no resources were silently omitted."
            )
        if prompt_length > 100000:  # Rough estimate for token limits
            print(f"Warning: Large prompt detected ({prompt_length} chars). Consider using plan-only mode for better performance.")
        
        # Determine model name based on provider
        model_name = self.config.foundry_deployment
        
        # Adjust parameters based on analysis depth (if configured)
        analysis_depth = getattr(self.config, 'analysis_depth', 'standard')
        if max_completion_tokens is not None:
            max_tokens = max_completion_tokens
        elif analysis_depth == 'quick':
            max_tokens = 4000
        elif analysis_depth == 'detailed':
            max_tokens = 12000
        else:  # standard
            max_tokens = 8000
        
        # Choose system message based on analysis style
        analysis_style = getattr(self.config, 'analysis_style', 'severity')
        
        # Load system prompt from file
        system_content = self.load_system_prompt(analysis_style)
        
        # Retry configuration
        try:
            max_retries = int(os.environ.get('API_MAX_RETRIES', '2'))
            timeout_seconds = int(os.environ.get('API_TIMEOUT_SECONDS', '120'))
        except ValueError as error:
            raise ValueError(
                "api-max-retries and api-timeout-seconds must be whole numbers"
            ) from error
        if max_retries < 1:
            raise ValueError("api-max-retries must be at least 1")
        if timeout_seconds < 1:
            raise ValueError("api-timeout-seconds must be at least 1")
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                print(f"Calling AI API (attempt {attempt + 1}/{max_retries})...")
                
                response = self.openai_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {
                            "role": "system", 
                            "content": system_content
                        },
                        {"role": "user", "content": scrubbed_prompt}
                    ],
                    max_completion_tokens=max_tokens,
                    timeout=timeout_seconds
                )
                
                content = response.choices[0].message.content
                if not isinstance(content, str) or not content.strip():
                    finish_reason = getattr(response.choices[0], "finish_reason", "unknown")
                    raise RuntimeError(
                        f"Foundry returned an empty completion (finish_reason={finish_reason})"
                    )
                return content
                
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
        
        safe_error = self._sanitize_error_message(str(last_error))
        raise RuntimeError(
            f"AI API failed after {max_retries} attempts: {safe_error}"
        ) from last_error
    
    def _sanitize_error_message(self, error_msg: str) -> str:
        """Remove sensitive information from error messages
        
        Args:
            error_msg: Raw error message that may contain sensitive data
            
        Returns:
            Sanitized error message safe for logging/display
        """
        sanitized = error_msg
        
        # Remove API keys (various formats)
        if self.config.foundry_api_key:
            sanitized = sanitized.replace(self.config.foundry_api_key, '***REDACTED***')
        
        # Remove endpoints/URLs (may contain sensitive paths)
        if self.config.foundry_endpoint:
            sanitized = sanitized.replace(self.config.foundry_endpoint, '***REDACTED_ENDPOINT***')
        
        # Remove file paths that may contain sensitive directory names
        sanitized = re.sub(r'/[a-zA-Z0-9/_-]+/terraform', '***/terraform', sanitized)
        sanitized = re.sub(r'C:\\[a-zA-Z0-9\\_-]+\\terraform', '***\\terraform', sanitized)
        
        # Remove any remaining patterns that look like API keys (alphanumeric 32+ chars)
        sanitized = re.sub(r'\b[A-Za-z0-9]{32,}\b', '***REDACTED***', sanitized)
        
        return sanitized

    def create_merge_prompt(self, batch_reports: List[str]) -> str:
        """Ask Foundry for one concise report from complete internal evidence."""
        evidence = "\n\n".join(
            f"Evidence report {index}:\n{report}"
            for index, report in enumerate(batch_reports, start=1)
        )
        prompt = (
            "Produce one concise Terraform review from the evidence reports below. "
            "Group repeated findings, retain affected resource addresses, and do not mention batches.\n\n"
            + evidence
        )
        if len(prompt) > self.config.max_prompt_chars:
            raise RuntimeError("Evidence reports exceed max-prompt-chars for the final merge")
        return prompt
    
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
        all_tf_files = self.read_terraform_files()

        # Detect cloud providers
        print("Detecting providers...")
        providers = CloudProviderDetector.detect_providers(all_tf_files, plan_data)

        # Format plan changes (counts/resource types) and build scrubbed, change-level
        # evidence for the prompt (sensitive values redacted, unknown values masked)
        print("Analysing plan changes...")
        _, resource_types, action_counts = self.format_plan_changes(plan_data)
        normalised_changes = [
            normalised for normalised in (
                normalise_plan_change(change) for change in plan_data.get('resource_changes', [])
            ) if normalised is not None
        ]

        # Get MCP insights if available
        mcp_results = {"status": "unavailable", "documents": [], "errors": ["Docker unavailable"]}
        if self.mcp_client:
            print("Getting insights from Terraform MCP server...")
            mcp_results = self.mcp_client.validate_plan_with_mcp(plan_data)
            mcp_status = mcp_results.get("status", "unavailable")
            if mcp_status == "available":
                print("Connected to HashiCorp MCP server via stdio protocol")

            elif mcp_status == "unavailable":
                print("Note: MCP server not available, continuing without MCP validation")
            elif mcp_status == "failed":
                print("Error: MCP server connection failed")
            else:
                print(f"MCP server status: {mcp_status}")
        
        prompts = self.build_prompt_batches(
            all_tf_files, normalised_changes, resource_types, action_counts, providers, mcp_results
        )

        # Analyse every batch. An error in any batch fails the whole review, so a
        # partial report is never presented as full coverage.
        print("Analysing with AI...")
        analyses = []
        for index, prompt in enumerate(prompts, start=1):
            print(f"Reviewing evidence batch {index}/{len(prompts)}...")
            analyses.append(self.analyse_with_ai(
                prompt, max_completion_tokens=4000 if len(prompts) > 1 else None
            ))
        ai_analysis = analyses[0] if len(prompts) == 1 else self.analyse_with_ai(
            self.create_merge_prompt(analyses), max_completion_tokens=12000
        )
        
        # Combine results
        final_analysis = f"## Terraform AI Plan Analysis\n\n"
        final_analysis += f"**Analysis Mode:** {self.config.analysis_mode.title()}\n"
        final_analysis += f"**Providers Detected:** {', '.join(providers) if providers else 'Unknown'}\n"
        final_analysis += f"**Analysis Focus:** {', '.join(self.config.analysis_focus)}\n\n"
        final_analysis += ai_analysis
        
        mcp_status = mcp_results.get("status", "unavailable")
        if mcp_status != "available":
            errors = mcp_results.get("errors", [])
            detail = errors[0] if errors else "Docker or the MCP server was unavailable"
            final_analysis += f"\n\n> Documentation enrichment unavailable: {detail}. The review continues using Terraform plan evidence.\n"

        summary = summarise_report(final_analysis, mcp_status=mcp_status)
        summary.update({
            "providers_detected": providers,
            "resource_changes": len(normalised_changes),
            "reviewed_resource_changes": len(normalised_changes),
            "review_batches": len(prompts),
            "review_status": "complete",
            "source_files_included": len(all_tf_files),
            "source_files_omitted": 0,
            "action_counts": action_counts,
            "review_configuration": {
                "analysis_preset": self.config.analysis_preset or "custom",
                "analysis_focus": self.config.analysis_focus,
                "analysis_mode": self.config.analysis_mode,
                "analysis_depth": self.config.analysis_depth,
                "analysis_style": self.config.analysis_style,
                "fail_on_severity": self.config.fail_on_severity,
                "request_strategy": "single-request" if len(prompts) == 1 else "size-packed",
                "max_prompt_chars": self.config.max_prompt_chars,
                "target_prompt_chars": self.config.target_prompt_chars,
                "max_resources_per_request": self.config.max_resources_per_request,
            },
            "severity_gate_triggered": severity_gate(summary, self.config.fail_on_severity),
        })

        with open('ai_analysis.md', 'w', encoding='utf-8') as f:
            f.write(final_analysis)
        with open('analysis_summary.json', 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)

        print("Analysis completed successfully!")
        return {"analysis": final_analysis, "summary": summary}


def load_config_from_env() -> AnalysisConfig:
    """Load and validate action configuration from environment variables."""
    ai_provider = os.environ.get("AI_PROVIDER", "foundry-openai").lower()
    if ai_provider != "foundry-openai":
        raise ValueError("ai-provider must be foundry-openai")

    plan_path = os.environ.get("TERRAFORM_PLAN_PATH", "tfplan.json")
    if not os.path.exists(plan_path):
        raise ValueError(f"Terraform plan not found at: {plan_path}")

    fail_on_severity = os.environ.get("FAIL_ON_SEVERITY", "none").lower()
    if fail_on_severity not in {"none", "warning", "critical"}:
        raise ValueError("fail-on-severity must be one of: none, warning, critical")

    analysis_depth = os.environ.get("ANALYSIS_DEPTH", "detailed").lower()
    if analysis_depth not in {"quick", "standard", "detailed"}:
        raise ValueError("analysis-depth must be one of: quick, standard, detailed")

    analysis_mode = os.environ.get("ANALYSIS_MODE", "plan-only").lower()
    analysis_style = os.environ.get("ANALYSIS_STYLE", "severity").lower()
    focus = resolve_analysis_preset(
        os.environ.get("ANALYSIS_PRESET", ""),
        os.environ.get("ANALYSIS_FOCUS", "security,cost,best-practices,deployment"),
    )
    return AnalysisConfig(
        ai_provider=ai_provider,
        foundry_api_key=os.environ.get("FOUNDRY_API_KEY"),
        foundry_endpoint=os.environ.get("FOUNDRY_ENDPOINT"),
        foundry_deployment=os.environ.get("FOUNDRY_DEPLOYMENT"),
        terraform_plan_path=plan_path,
        terraform_directory=os.environ.get("TERRAFORM_DIRECTORY", "."),
        analysis_focus=focus.split(","),
        analysis_preset=os.environ.get("ANALYSIS_PRESET", ""),
        analysis_mode=analysis_mode,
        analysis_depth=analysis_depth,
        analysis_style=analysis_style,
        fail_on_severity=fail_on_severity,
        mcp_available=os.environ.get("MCP_AVAILABLE", "false").lower() == "true",
        skip_mcp=os.environ.get("SKIP_MCP", "false").lower() == "true",
        max_prompt_chars=int(os.environ.get("MAX_PROMPT_CHARS", "120000")),
        target_prompt_chars=int(os.environ.get("TARGET_PROMPT_CHARS", "100000")),
        max_resources_per_request=int(os.environ.get("MAX_RESOURCES_PER_REQUEST", "100")),
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
