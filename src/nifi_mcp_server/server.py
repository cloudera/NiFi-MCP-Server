from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import anyio

from .config import ServerConfig
from .auth import KnoxAuthFactory
from .client import NiFiClient
from .flow_builder import analyze_flow_request
from .best_practices import NiFiBestPractices, SmartFlowBuilder
from .setup_helper import SetupGuide


# Lazy import of MCP to give a clear error if the dependency is missing
try:
	# FastMCP is exposed from its dedicated module in current MCP SDK releases.
	try:
		from mcp.server.fastmcp import FastMCP
	except ImportError:  # compatibility with SDK releases that re-exported it
		from mcp.server import FastMCP
	from mcp.server.stdio import stdio_server
except Exception as e:  # pragma: no cover
	raise RuntimeError(
		"The 'mcp' package is required. Install with: pip install mcp"
	) from e


def _redact_sensitive(obj: Any, max_items: int = 200) -> Any:
	"""Redact common sensitive fields and truncate large collections for LLMs."""
	# Normalize key names so camelCase, snake_case, hyphenated and mixed-case
	# variants receive the same treatment. Match suffixes, not arbitrary substrings
	# (e.g. do not redact a harmless field named "tokenizerMode").
	sensitive_names = {
		"password", "passwd", "passphrase", "passcode", "token", "secret",
		"apikey", "authorization", "cookie", "privatekey", "kerberoskeytab",
		"sslkeystorepasswd", "keystorepassword", "truststorepassword",
	}
	if isinstance(obj, dict):
		redacted: Dict[str, Any] = {}
		for k, v in obj.items():
			normalized_key = "".join(ch for ch in str(k).lower() if ch.isalnum())
			is_sensitive = (
				normalized_key in sensitive_names
				or any(normalized_key.endswith(suffix) for suffix in (
					"password", "passwd", "passphrase", "passcode", "token",
					"secret", "apikey", "authorization", "cookie", "privatekey", "keytab"
				))
			)
			if is_sensitive:
				redacted[k] = "***REDACTED***"
			else:
				redacted[k] = _redact_sensitive(v, max_items)
		return redacted
	if isinstance(obj, list):
		if len(obj) > max_items:
			return [_redact_sensitive(x, max_items) for x in obj[:max_items]] + [
				{"truncated": True, "omitted_count": len(obj) - max_items}
			]
		return [_redact_sensitive(x, max_items) for x in obj]
	return obj


def build_client(config: ServerConfig) -> NiFiClient:
	verify = config.build_verify()
	nifi_base = config.build_nifi_base()
	auth = KnoxAuthFactory(
		gateway_url=config.knox_gateway_url,
		token=config.knox_token,
		cookie=config.knox_cookie,
		user=config.knox_user,
		password=config.knox_password,
		token_endpoint=config.knox_token_endpoint,
		passcode_token=config.knox_passcode_token,
		verify=verify,
		nifi_api_base=nifi_base,
		nifi_user=config.nifi_username,
		nifi_password=config.nifi_password,
		client_cert=config.nifi_client_cert,
		client_key=config.nifi_client_key,
	)
	session = auth.build_session()
	return NiFiClient(
		nifi_base,
		session,
		timeout_seconds=config.timeout_seconds,
		proxy_context_path=config.proxy_context_path,
	)


def create_server(nifi: NiFiClient, readonly: bool, allowed_actions_csv: str = "") -> FastMCP:
	app = FastMCP("nifi-mcp-server")
	allowed_actions = {item.strip().casefold() for item in allowed_actions_csv.split(",") if item.strip()}
	known_write_actions: set[str] = set()

	def write_tool():
		"""Register a mutation tool only when the optional action allowlist permits it."""
		def decorator(func):
			action_name = func.__name__.casefold()
			known_write_actions.add(action_name)
			if not allowed_actions or action_name in allowed_actions:
				return app.tool()(func)
			return func
		return decorator

	@app.tool()
	async def get_nifi_version() -> Dict[str, Any]:
		"""Get NiFi version and build information. Works with both NiFi 1.x and 2.x."""
		data = nifi.get_version_info()
		version_tuple = nifi.get_version_tuple()
		is_2x = nifi.is_nifi_2x()
		return {
			"version_info": _redact_sensitive(data),
			"parsed_version": f"{version_tuple[0]}.{version_tuple[1]}.{version_tuple[2]}",
			"is_nifi_2x": is_2x,
			"major_version": version_tuple[0],
		}

	@app.tool()
	async def get_root_process_group() -> Dict[str, Any]:
		"""Return the root process group (read-only). Works with both NiFi 1.x and 2.x."""
		data = nifi.get_root_process_group()
		return _redact_sensitive(data)

	@app.tool()
	async def list_processors(process_group_id: str) -> Dict[str, Any]:
		"""List processors in a process group (read-only). Works with both NiFi 1.x and 2.x."""
		data = nifi.list_processors(process_group_id)
		return _redact_sensitive(data)

	@app.tool()
	async def list_connections(process_group_id: str) -> Dict[str, Any]:
		"""List connections in a process group (read-only). Works with both NiFi 1.x and 2.x."""
		data = nifi.list_connections(process_group_id)
		return _redact_sensitive(data)

	@app.tool()
	async def get_bulletins(after_ms: Optional[int] = None) -> Dict[str, Any]:
		"""Get recent bulletins since a timestamp in ms (read-only). Works with both NiFi 1.x and 2.x."""
		data = nifi.get_bulletins(after_ms)
		return _redact_sensitive(data)

	@app.tool()
	async def list_parameter_contexts() -> Dict[str, Any]:
		"""List parameter contexts (read-only). Works with both NiFi 1.x and 2.x. Note: schema may differ slightly between versions."""
		data = nifi.list_parameter_contexts()
		return _redact_sensitive(data)

	@app.tool()
	async def get_controller_services(process_group_id: Optional[str] = None) -> Dict[str, Any]:
		"""Get controller services (read-only). If process_group_id is None, returns controller-level services. Works with both NiFi 1.x and 2.x."""
		data = nifi.get_controller_services(process_group_id)
		return _redact_sensitive(data)

	# ===== Additional Read-Only Tools =====

	@app.tool()
	async def get_processor_types() -> Dict[str, Any]:
		"""Get all available processor types (read-only). Useful for discovering what processors can be created."""
		data = nifi.get_processor_types()
		return _redact_sensitive(data)

	@app.tool()
	async def search_flow(query: str) -> Dict[str, Any]:
		"""Search the NiFi flow for components (read-only). Returns processors, connections, and other components matching the search query."""
		data = nifi.search_flow(query)
		return _redact_sensitive(data)

	@app.tool()
	async def get_connection_details(connection_id: str) -> Dict[str, Any]:
		"""Get details about a specific connection including queue size and relationships (read-only)."""
		data = nifi.get_connection(connection_id)
		return _redact_sensitive(data)

	@app.tool()
	async def get_processor_details(processor_id: str) -> Dict[str, Any]:
		"""Get detailed information about a specific processor including configuration (read-only)."""
		data = nifi.get_processor(processor_id)
		return _redact_sensitive(data)

	@app.tool()
	async def list_input_ports(process_group_id: str) -> Dict[str, Any]:
		"""List input ports for a process group (read-only)."""
		data = nifi.get_input_ports(process_group_id)
		return _redact_sensitive(data)

	@app.tool()
	async def list_output_ports(process_group_id: str) -> Dict[str, Any]:
		"""List output ports for a process group (read-only)."""
		data = nifi.get_output_ports(process_group_id)
		return _redact_sensitive(data)
	
	@app.tool()
	async def get_processor_state(processor_id: str) -> str:
		"""Get just the state of a processor (RUNNING, STOPPED, DISABLED, etc.).
		
		Quick status check without fetching full processor details.
		"""
		return nifi.get_processor_state(processor_id)
	
	@app.tool()
	async def check_connection_queue(connection_id: str) -> Dict[str, int]:
		"""Check queue size for a connection (flowfile count and bytes).
		
		Useful before deleting connections - they must be empty to delete.
		Returns: {'flowFilesQueued': int, 'bytesQueued': int}
		"""
		return nifi.get_connection_queue_size(connection_id)
	
	@app.tool()
	async def get_flow_summary(process_group_id: str) -> Dict[str, Any]:
		"""Get summary statistics for a process group.
		
		Returns processor counts by state, connection count, and total queued data.
		Perfect for understanding the overall health and state of a flow.
		"""
		return nifi.get_process_group_summary(process_group_id)
	
	@app.tool()
	async def analyze_flow_build_request(user_request: str) -> Dict[str, Any]:
		"""Analyze a user's request to build a NiFi flow and provide guidance.
		
		This tool identifies common flow patterns (SQL to Iceberg, Kafka to S3, etc.)
		and returns the requirements needed to build the flow.
		
		Examples:
		  - "Build a flow from SQL Server to Iceberg"
		  - "I need to move data from Kafka to S3"
		  - "Create a REST API to database pipeline"
		  
		Returns requirements the user needs to provide before building the flow.
		Use this BEFORE attempting to create processors for complex flows.
		"""
		return analyze_flow_request(user_request)
	
	@app.tool()
	async def get_setup_instructions() -> str:
		"""Get comprehensive setup instructions for configuring the NiFi MCP Server.
		
		Use this when:
		  - User asks "how do I configure this?"
		  - Connection errors suggest missing configuration
		  - User needs help with environment variables
		
		Returns detailed setup guide with examples for CDP NiFi and standalone NiFi.
		"""
		return SetupGuide.get_setup_instructions()
	
	@app.tool()
	async def check_configuration() -> Dict[str, Any]:
		"""Check current NiFi MCP Server configuration and validate it.
		
		Use this when:
		  - User asks "is my configuration correct?"
		  - Troubleshooting connection issues
		  - Before attempting to connect to NiFi
		
		Returns validation results with errors and warnings.
		"""
		is_valid, errors, warnings = SetupGuide.validate_current_config()
		return {
			"is_valid": is_valid,
			"errors": errors,
			"warnings": warnings,
			"message": "Configuration is valid" if is_valid else "Configuration has errors"
		}
	
	@app.tool()
	async def get_best_practices_guide() -> str:
		"""Get NiFi flow building best practices guide.
		
		Use this when:
		  - User asks "what are best practices?"
		  - User is building their first flow
		  - User wants to understand proper flow organization
		
		Returns comprehensive guide covering process groups, naming, lifecycle, etc.
		"""
		return NiFiBestPractices.get_best_practices_guide()
	
	@app.tool()
	async def get_recommended_workflow(user_request: str) -> str:
		"""Get recommended step-by-step workflow for building a specific flow.
		
		Use this when:
		  - User asks "how should I build this flow?"
		  - User needs guidance on the order of operations
		  - User is unsure where to start
		
		Args:
		  user_request: Description of the flow the user wants to build
		
		Returns step-by-step workflow with best practices.
		"""
		return NiFiBestPractices.get_recommended_workflow_for_request(user_request)

	# ===== Write Tools (only enabled when NIFI_READONLY=false) =====

	if not readonly:
		@write_tool()
		async def start_processor(processor_id: str, version: int) -> Dict[str, Any]:
			"""Start a processor. **WRITE OPERATION** - Requires NIFI_READONLY=false."""
			data = nifi.start_processor(processor_id, version)
			return _redact_sensitive(data)

		@write_tool()
		async def stop_processor(processor_id: str, version: int) -> Dict[str, Any]:
			"""Stop a processor. **WRITE OPERATION** - Requires NIFI_READONLY=false."""
			data = nifi.stop_processor(processor_id, version)
			return _redact_sensitive(data)

		@write_tool()
		async def create_processor(
			process_group_id: str,
			processor_type: str,
			name: str,
			position_x: float = 0.0,
			position_y: float = 0.0
		) -> Dict[str, Any]:
			"""Create a new processor in a process group. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Args:
				process_group_id: The ID of the process group to create the processor in
				processor_type: The fully qualified processor type (e.g., 'org.apache.nifi.processors.standard.LogAttribute')
				name: The name for the new processor
				position_x: X coordinate on the canvas (default: 0.0)
				position_y: Y coordinate on the canvas (default: 0.0)
			"""
			data = nifi.create_processor(process_group_id, processor_type, name, position_x, position_y)
			return _redact_sensitive(data)

		@write_tool()
		async def update_processor_config(
			processor_id: str,
			version: int,
			config: Dict[str, Any]
		) -> Dict[str, Any]:
			"""Update processor configuration. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Args:
				processor_id: The processor ID
				version: The current revision version
				config: Configuration object with properties, scheduling strategy, etc.
			"""
			data = nifi.update_processor(processor_id, version, config)
			return _redact_sensitive(data)

		@write_tool()
		async def delete_processor(processor_id: str, version: int) -> Dict[str, Any]:
			"""Delete a processor. **WRITE OPERATION** - Requires NIFI_READONLY=false."""
			data = nifi.delete_processor(processor_id, version)
			return _redact_sensitive(data)

		@write_tool()
		async def create_connection(
			process_group_id: str,
			source_id: str,
			source_type: str,
			destination_id: str,
			destination_type: str,
			relationships: str
		) -> Dict[str, Any]:
			"""Create a connection between two components. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Args:
				process_group_id: The process group ID
				source_id: Source component ID
				source_type: Source type (PROCESSOR, INPUT_PORT, OUTPUT_PORT, FUNNEL)
				destination_id: Destination component ID
				destination_type: Destination type (PROCESSOR, INPUT_PORT, OUTPUT_PORT, FUNNEL)
				relationships: Comma-separated list of relationships (e.g., 'success,failure')
			"""
			rel_list = [r.strip() for r in relationships.split(',')]
			data = nifi.create_connection(
				process_group_id, source_id, source_type,
				destination_id, destination_type, rel_list
			)
			return _redact_sensitive(data)

		@write_tool()
		async def delete_connection(connection_id: str, version: int) -> Dict[str, Any]:
			"""Delete a connection. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Note: Connections with flowfiles in the queue cannot be deleted.
			Check queue status with get_connection_details() first, or use empty_connection_queue().
			"""
			data = nifi.delete_connection(connection_id, version)
			return _redact_sensitive(data)

		@write_tool()
		async def empty_connection_queue(connection_id: str) -> Dict[str, Any]:
			"""Drop all flowfiles from a connection's queue. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			⚠️ WARNING: This permanently deletes flowfiles. Use before deleting connections with queued data.
			"""
			data = nifi.empty_connection_queue(connection_id)
			return _redact_sensitive(data)

		@write_tool()
		async def enable_controller_service(service_id: str, version: int) -> Dict[str, Any]:
			"""Enable a controller service. **WRITE OPERATION** - Requires NIFI_READONLY=false."""
			data = nifi.enable_controller_service(service_id, version)
			return _redact_sensitive(data)

		@write_tool()
		async def disable_controller_service(service_id: str, version: int) -> Dict[str, Any]:
			"""Disable a controller service. **WRITE OPERATION** - Requires NIFI_READONLY=false."""
			data = nifi.disable_controller_service(service_id, version)
			return _redact_sensitive(data)
		
		@write_tool()
		async def create_controller_service(process_group_id: str, service_type: str, name: str) -> Dict[str, Any]:
			"""Create a controller service in a process group. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Common service types:
			  - org.apache.nifi.dbcp.DBCPConnectionPool (Database connections)
			  - org.apache.nifi.json.JsonRecordSetWriter (JSON output)
			  - org.apache.nifi.avro.AvroRecordSetWriter (Avro output)
			  - org.apache.nifi.csv.CSVRecordSetWriter (CSV output)
			  - org.apache.nifi.json.JsonTreeReader (JSON input)
			  - org.apache.nifi.avro.AvroReader (Avro input)
			  - org.apache.nifi.csv.CSVReader (CSV input)
			
			Returns the created service with ID for configuration.
			"""
			data = nifi.create_controller_service(process_group_id, service_type, name)
			return _redact_sensitive(data)
		
		@write_tool()
		async def update_controller_service_properties(service_id: str, version: int, properties: Dict[str, str]) -> Dict[str, Any]:
			"""Update controller service properties. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Note: Service must be in DISABLED state to update properties.
			Use get_controller_service() to see available properties and current values.
			"""
			data = nifi.update_controller_service(service_id, version, properties)
			return _redact_sensitive(data)
		
	@app.tool()
	async def get_controller_service_details(service_id: str) -> Dict[str, Any]:
		"""Get detailed controller service information including properties and state.
		
		Use this to check current configuration before updates.
		"""
		data = nifi.get_controller_service(service_id)
		return _redact_sensitive(data)
	
	@app.tool()
	async def find_controller_services_by_type(process_group_id: str, service_type: str) -> Dict[str, Any]:
		"""Find controller services by type to check if they already exist (read-only).
		
		Use this BEFORE creating controller services to avoid 409 Conflict errors.
		
		Args:
			process_group_id: Process group ID (use "root" for controller-level)
			service_type: Full service type name (e.g., "org.apache.nifi.distributed.cache.server.map.DistributedMapCacheServer")
		
		Returns list of matching services with their IDs, names, and states.
		
		Example:
			Before creating a DistributedMapCacheServer, check if one already exists:
			find_controller_services_by_type("root", "org.apache.nifi.distributed.cache.server.map.DistributedMapCacheServer")
		"""
		pg_id = None if process_group_id.lower() == "root" else process_group_id
		matches = nifi.find_controller_services_by_type(pg_id, service_type)
		
		# Simplify output for LLM consumption
		simplified = []
		for svc in matches:
			component = svc.get("component", {})
			simplified.append({
				"id": component.get("id"),
				"name": component.get("name"),
				"type": component.get("type"),
				"state": component.get("state"),
				"version": svc.get("revision", {}).get("version")
			})
		
		return {
			"count": len(simplified),
			"services": simplified,
			"message": f"Found {len(simplified)} existing service(s) of type {service_type}"
		}
	
	if not readonly:
		@write_tool()
		async def delete_controller_service(service_id: str, version: int) -> Dict[str, Any]:
			"""Delete a controller service. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Prerequisites:
			  - Service must be DISABLED
			  - No processors can reference this service
			"""
			data = nifi.delete_controller_service(service_id, version)
			return _redact_sensitive(data)
		
		@write_tool()
		async def start_new_flow(flow_name: str, parent_pg_id: str = None) -> Dict[str, Any]:
			"""Start a new NiFi flow following best practices. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			🌟 RECOMMENDED WAY to start building flows!
			
			This tool automatically:
			  1. Creates a process group for your flow (best practice!)
			  2. Returns the group ID for adding components
			  3. Provides next steps guidance
			
			Use this INSTEAD of creating processors directly on root canvas.
			
			Args:
			  flow_name: Descriptive name for your flow (e.g., "ETL Pipeline", "Kafka Integration")
			  parent_pg_id: Optional parent process group (defaults to root)
			
			Example: start_new_flow("Data Ingestion Pipeline")
			"""
			smart_builder = SmartFlowBuilder(nifi)
			result = smart_builder.start_new_flow(flow_name, parent_pg_id)
			return _redact_sensitive(result)
		
		@write_tool()
		async def create_process_group(parent_id: str, name: str, position_x: float = 0.0, position_y: float = 0.0) -> Dict[str, Any]:
			"""Create a process group (folder) for organizing flows. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Process groups allow you to organize flows into logical sections:
			  - Separate dev/test/prod environments
			  - Group related processors
			  - Create modular, reusable flow components
			
			💡 TIP: Consider using start_new_flow() instead - it follows best practices automatically!
			
			Returns the created process group with ID for adding processors.
			"""
			data = nifi.create_process_group(parent_id, name, position_x, position_y)
			return _redact_sensitive(data)
		
		@write_tool()
		async def update_process_group_name(pg_id: str, version: int, name: str) -> Dict[str, Any]:
			"""Rename a process group. **WRITE OPERATION** - Requires NIFI_READONLY=false."""
			data = nifi.update_process_group(pg_id, version, name)
			return _redact_sensitive(data)
		
		@write_tool()
		async def delete_process_group(pg_id: str, version: int) -> Dict[str, Any]:
			"""Delete a process group. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Prerequisites:
			  - Process group must be empty (no processors, connections, or child groups)
			  - All components must be stopped
			
			Use this to clean up empty organizational groups.
			"""
			data = nifi.delete_process_group(pg_id, version)
			return _redact_sensitive(data)
		
		@write_tool()
		async def create_input_port(pg_id: str, name: str, position_x: float = 0.0, position_y: float = 0.0) -> Dict[str, Any]:
			"""Create an input port for inter-process-group communication. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Input ports allow child process groups to receive data from parent groups.
			Connect processors in parent group to this port to send data into the child group.
			"""
			data = nifi.create_input_port(pg_id, name, position_x, position_y)
			return _redact_sensitive(data)
		
		@write_tool()
		async def create_output_port(pg_id: str, name: str, position_x: float = 0.0, position_y: float = 0.0) -> Dict[str, Any]:
			"""Create an output port for inter-process-group communication. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Output ports allow child process groups to send data to parent groups.
			Connect processors to this port, then connect the port to processors in parent group.
			"""
			data = nifi.create_output_port(pg_id, name, position_x, position_y)
			return _redact_sensitive(data)
		
		@write_tool()
		async def update_input_port(port_id: str, version: int, name: str) -> Dict[str, Any]:
			"""Update (rename) an input port. **WRITE OPERATION** - Requires NIFI_READONLY=false."""
			data = nifi.update_input_port(port_id, version, name)
			return _redact_sensitive(data)
		
		@write_tool()
		async def update_output_port(port_id: str, version: int, name: str) -> Dict[str, Any]:
			"""Update (rename) an output port. **WRITE OPERATION** - Requires NIFI_READONLY=false."""
			data = nifi.update_output_port(port_id, version, name)
			return _redact_sensitive(data)
		
		@write_tool()
		async def delete_input_port(port_id: str, version: int) -> Dict[str, Any]:
			"""Delete an input port. **WRITE OPERATION** - Requires NIFI_READONLY=false."""
			data = nifi.delete_input_port(port_id, version)
			return _redact_sensitive(data)
		
		@write_tool()
		async def delete_output_port(port_id: str, version: int) -> Dict[str, Any]:
			"""Delete an output port. **WRITE OPERATION** - Requires NIFI_READONLY=false."""
			data = nifi.delete_output_port(port_id, version)
			return _redact_sensitive(data)
		
		@write_tool()
		async def get_parameter_context_details(context_id: str) -> Dict[str, Any]:
			"""Get parameter context with all parameters."""
			data = nifi.get_parameter_context(context_id)
			return _redact_sensitive(data)
		
		@write_tool()
		async def create_parameter_context(name: str, description: str = "", parameters: str = "[]") -> Dict[str, Any]:
			"""Create a parameter context for environment-specific configuration. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Parameters should be JSON array of objects with 'name', 'value', 'sensitive' fields.
			Example: '[{"name":"db.host","value":"localhost","sensitive":false}]'
			
			Use cases:
			  - Store database connection strings
			  - Environment-specific URLs
			  - API keys (use sensitive:true)
			"""
			import json
			params_list = json.loads(parameters) if parameters != "[]" else None
			data = nifi.create_parameter_context(name, description, params_list)
			return _redact_sensitive(data)
		
		@write_tool()
		async def update_parameter_context(context_id: str, version: int, name: str = None, parameters: str = None) -> Dict[str, Any]:
			"""Update parameter context. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Parameters should be JSON array if provided.
			"""
			import json
			params_list = json.loads(parameters) if parameters else None
			data = nifi.update_parameter_context(context_id, version, name, None, params_list)
			return _redact_sensitive(data)
		
		@write_tool()
		async def delete_parameter_context(context_id: str, version: int) -> Dict[str, Any]:
			"""Delete a parameter context. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Note: Context must not be referenced by any process groups.
			"""
			data = nifi.delete_parameter_context(context_id, version)
			return _redact_sensitive(data)
		
		@write_tool()
		async def start_input_port(port_id: str, version: int) -> Dict[str, Any]:
			"""Start an input port to enable data flow. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Ports are created in STOPPED state by default and must be started to receive data.
			"""
			data = nifi.start_input_port(port_id, version)
			return _redact_sensitive(data)
		
		@write_tool()
		async def stop_input_port(port_id: str, version: int) -> Dict[str, Any]:
			"""Stop an input port to disable data flow. **WRITE OPERATION** - Requires NIFI_READONLY=false."""
			data = nifi.stop_input_port(port_id, version)
			return _redact_sensitive(data)
		
		@write_tool()
		async def start_output_port(port_id: str, version: int) -> Dict[str, Any]:
			"""Start an output port to enable data flow. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			Ports are created in STOPPED state by default and must be started to send data.
			"""
			data = nifi.start_output_port(port_id, version)
			return _redact_sensitive(data)
		
		@write_tool()
		async def stop_output_port(port_id: str, version: int) -> Dict[str, Any]:
			"""Stop an output port to disable data flow. **WRITE OPERATION** - Requires NIFI_READONLY=false."""
			data = nifi.stop_output_port(port_id, version)
			return _redact_sensitive(data)
		
		@write_tool()
		async def apply_parameter_context_to_process_group(pg_id: str, pg_version: int, context_id: str) -> Dict[str, Any]:
			"""Apply a parameter context to a process group. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			This enables the process group and its processors to reference parameters using #{param_name} syntax.
			
			Example workflow:
			  1. Create parameter context with db credentials
			  2. Apply context to process group
			  3. Use #{db.host}, #{db.password} in processor properties
			"""
			data = nifi.apply_parameter_context_to_process_group(pg_id, pg_version, context_id)
			return _redact_sensitive(data)
		
		@write_tool()
		async def start_all_processors_in_group(pg_id: str) -> Dict[str, Any]:
			"""Start ALL processors in a process group at once. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			This is a BULK operation that starts all processors simultaneously, much faster than starting individually.
			
			Returns counts of:
			  - started: Successfully started processors
			  - already_running: Processors that were already running
			  - failed: Processors that failed to start (with error messages)
			
			Use case: "Start all processors in my ETL group"
			"""
			data = nifi.start_all_processors_in_group(pg_id)
			return _redact_sensitive(data)
		
		@write_tool()
		async def stop_all_processors_in_group(pg_id: str) -> Dict[str, Any]:
			"""Stop ALL processors in a process group at once. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			This is a BULK operation that stops all processors simultaneously, much faster than stopping individually.
			
			Returns counts of:
			  - stopped: Successfully stopped processors
			  - already_stopped: Processors that were already stopped
			  - failed: Processors that failed to stop (with error messages)
			
			Use case: "Stop all processors before making changes"
			"""
			data = nifi.stop_all_processors_in_group(pg_id)
			return _redact_sensitive(data)
		
		@write_tool()
		async def enable_all_controller_services_in_group(pg_id: str) -> Dict[str, Any]:
			"""Enable ALL controller services in a process group at once. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			This is a BULK operation that enables all services simultaneously.
			
			Returns counts of:
			  - enabled: Successfully enabled services
			  - already_enabled: Services that were already enabled
			  - failed: Services that failed to enable (with error messages)
			
			Use case: "Enable all services before starting flow"
			"""
			data = nifi.enable_all_controller_services_in_group(pg_id)
			return _redact_sensitive(data)
		
		@write_tool()
		async def terminate_processor(processor_id: str, version: int) -> Dict[str, Any]:
			"""Forcefully terminate a stuck processor. **WRITE OPERATION** - Requires NIFI_READONLY=false.
			
			⚠️ WARNING: Last-resort operation for processors that won't stop normally!
			
			Use only when:
			  - Processor is stuck and not responding
			  - Normal stop command doesn't work
			  - Processor threads need to be killed
			
			The operation first tries a normal stop, only terminates if that fails.
			
			Use case: "My processor is stuck and won't stop, force terminate it"
			"""
			data = nifi.terminate_processor(processor_id, version)
			return _redact_sensitive(data)

		@write_tool()
		async def replay_flowfile_from_provenance(event_id: str) -> Dict[str, Any]:
			"""Re-queue a new flowfile from a provenance event's content. **WRITE OPERATION** - Requires NIFI_READONLY=false.

			Only works if the event's source connection still exists - call get_provenance_event_details(event_id)
			first and check the "replayAvailable" field (its "replayExplanation" field says why not, if false).

			Use case: "Replay that failed flowfile through the flow again"
			"""
			data = nifi.replay_flowfile_from_provenance(event_id)
			return _redact_sensitive(data)

		@write_tool()
		async def reset_counter(counter_id: str) -> Dict[str, Any]:
			"""Reset a single NiFi counter's value to 0. **WRITE OPERATION** - Requires NIFI_READONLY=false."""
			data = nifi.reset_counter(counter_id)
			return _redact_sensitive(data)

	# Read-only health monitoring tool (available even in readonly mode)
	@app.tool()
	async def get_flow_health_status(pg_id: str) -> Dict[str, Any]:
		"""Get comprehensive health status of a process group and all its components.
		
		Returns detailed health information:
		  - Processor status (running/stopped/invalid/disabled counts)
		  - Controller service status (enabled/disabled/invalid counts)
		  - Connection queue status (queued data, backpressure)
		  - Recent bulletins and errors
		  - Overall health assessment (HEALTHY | DEGRADED | UNHEALTHY)
		
		Use cases:
		  - "Is my flow healthy?"
		  - "Show me flow status"
		  - "What's broken in my pipeline?"
		  - "Check for errors in my data ingestion group"
		"""
		data = nifi.get_flow_health_status(pg_id)
		return _redact_sensitive(data)

	# ===== FlowFile Queue & Provenance (Debug Tools, read-only) =====

	@app.tool()
	async def list_queue_flowfiles(connection_id: str, max_results: int = 100) -> Dict[str, Any]:
		"""List flowfiles currently sitting in a connection's queue (read-only).

		Returns up to max_results flowfile summaries (uuid, filename, size, position, how long
		queued). NiFi itself caps a single listing at 100 flowfiles.

		Use cases:
		  - "What's stuck in this queue?"
		  - "Show me the flowfiles waiting in connection abc-123"
		"""
		data = nifi.list_queue_flowfiles(connection_id, max_results=max_results)
		return _redact_sensitive(data)

	@app.tool()
	async def get_flowfile_details(connection_id: str, flowfile_uuid: str) -> Dict[str, Any]:
		"""Get metadata and attributes for a single queued flowfile (read-only).

		Get the flowfile_uuid from list_queue_flowfiles() first.
		"""
		data = nifi.get_flowfile_details(connection_id, flowfile_uuid)
		return _redact_sensitive(data)

	@app.tool()
	async def get_flowfile_content(connection_id: str, flowfile_uuid: str, max_bytes: int = 8192) -> Dict[str, Any]:
		"""Download the content of a single queued flowfile (read-only).

		Content is truncated to max_bytes and returned as UTF-8 text when possible, otherwise
		base64-encoded (check the "encoding" field of the result). Get the flowfile_uuid from
		list_queue_flowfiles() first.
		"""
		return nifi.get_flowfile_content(connection_id, flowfile_uuid, max_bytes=max_bytes)

	@app.tool()
	async def search_provenance(
		component_id: Optional[str] = None,
		flowfile_uuid: Optional[str] = None,
		search_terms: Optional[Dict[str, str]] = None,
		start_date: Optional[str] = None,
		end_date: Optional[str] = None,
		max_results: int = 100,
	) -> Dict[str, Any]:
		"""Search provenance events (read-only) - answers "where did this flowfile come from",
		"why did it fail", "what happened to it".

		Args:
		  component_id: filter to events produced by a specific processor (its ID)
		  flowfile_uuid: filter to a specific flowfile's full lineage (its UUID)
		  search_terms: raw field->value map for other NiFi provenance search fields
		    (e.g. {"Filename": "orders.csv", "EventType": "DROP"})
		  start_date/end_date: NiFi provenance date format, e.g. "09/11/2026 00:00:00 UTC"
		  max_results: maximum number of events to return (default 100)

		Returns a list of provenance events (each with an "id" usable with
		get_provenance_event_details()). At least one filter is strongly recommended -
		an unfiltered search can be slow on a busy NiFi instance.

		Use cases:
		  - "Why did flowfile abc-123 fail?"
		  - "What happened to files processed by processor xyz-789 in the last hour?"
		"""
		data = nifi.search_provenance(
			search_terms=search_terms,
			component_id=component_id,
			flowfile_uuid=flowfile_uuid,
			start_date=start_date,
			end_date=end_date,
			max_results=max_results,
		)
		return _redact_sensitive(data)

	@app.tool()
	async def get_provenance_event_details(event_id: str) -> Dict[str, Any]:
		"""Get full details for a single provenance event (read-only): attributes, the
		component that produced it, and whether its flowfile content can still be downloaded
		(inputContentAvailable/outputContentAvailable) or replayed (replayAvailable).

		Get the event_id from search_provenance() first.
		"""
		data = nifi.get_provenance_event(event_id)
		return _redact_sensitive(data)

	@app.tool()
	async def get_provenance_event_content(event_id: str, direction: str = "output", max_bytes: int = 8192) -> Dict[str, Any]:
		"""Download the flowfile content snapshot associated with a provenance event (read-only).

		Args:
		  event_id: from search_provenance()
		  direction: "input" or "output" - check inputContentAvailable/outputContentAvailable
		    on get_provenance_event_details(event_id) first to see which are available
		  max_bytes: truncate content to this size (default 8192)
		"""
		return nifi.get_provenance_event_content(event_id, direction=direction, max_bytes=max_bytes)

	# ===== Operational Diagnostics (read-only) =====

	@app.tool()
	async def get_system_diagnostics() -> Dict[str, Any]:
		"""Get JVM/host diagnostics for the NiFi instance (read-only): heap/CPU usage, garbage
		collection, disk usage for the flowfile/content/provenance repositories, uptime.

		Use cases:
		  - "Is NiFi running low on disk space?"
		  - "How's the heap usage looking?"
		"""
		data = nifi.get_system_diagnostics()
		return _redact_sensitive(data)

	@app.tool()
	async def get_processor_diagnostics(processor_id: str) -> Dict[str, Any]:
		"""Get deep diagnostics for a single processor (read-only): thread dumps for any active
		threads, referenced controller services, and incoming/outgoing connection status.

		Use this to investigate a processor that appears stuck or unresponsive, before
		resorting to terminate_processor().
		"""
		data = nifi.get_processor_diagnostics(processor_id)
		return _redact_sensitive(data)

	@app.tool()
	async def get_cluster_summary() -> Dict[str, Any]:
		"""Get cluster status (read-only): whether this NiFi is clustered, and connected/total node counts."""
		data = nifi.get_cluster_summary()
		return _redact_sensitive(data)

	@app.tool()
	async def list_cluster_nodes() -> Dict[str, Any]:
		"""List cluster nodes and their status (read-only): heartbeat, connection state, load.

		Returns {"clustered": false} for a standalone (non-clustered) NiFi instance rather
		than an error.
		"""
		data = nifi.list_cluster_nodes()
		return _redact_sensitive(data)

	@app.tool()
	async def list_counters() -> Dict[str, Any]:
		"""List all NiFi counters (read-only). Counters are lightweight named tallies some
		processors increment (e.g. records read/written) - useful for monitoring throughput.
		"""
		data = nifi.list_counters()
		return _redact_sensitive(data)

	if not readonly and allowed_actions:
		unknown_actions = sorted(allowed_actions - known_write_actions)
		if unknown_actions:
			unknown = ", ".join(unknown_actions)
			raise ValueError(f"NIFI_ALLOWED_ACTIONS contains unknown write tool name(s): {unknown}")

	return app


async def run_stdio() -> None:
	# For FastMCP, prefer the built-in stdio runner
	config = ServerConfig()
	nifi = build_client(config)
	server = create_server(nifi, readonly=config.readonly, allowed_actions_csv=config.allowed_actions_csv)
	# run() is synchronous; call the async flavor directly
	await server.run_stdio_async()


def main() -> None:
	transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
	if transport != "stdio":
		# Defer to FastMCP synchronous run helper for other transports when added
		config = ServerConfig()
		nifi = build_client(config)
		server = create_server(nifi, readonly=config.readonly)
		server.run(transport=transport)
		return
	anyio.run(run_stdio)


if __name__ == "__main__":
	main()


