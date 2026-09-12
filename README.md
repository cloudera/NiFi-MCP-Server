# NiFi MCP Server

Model Context Protocol server providing selectable read and write access to Apache NiFi. Works with NiFi behind Apache Knox (CDP) **and** with a standalone/local NiFi instance with no Knox in front of it.

**Works with both NiFi 1.x and 2.x** - automatic version detection and adaptation.

![](/screenshots/Nifi-meet-mcp.png)

## Features

- **Automatic version detection** - Detects NiFi 1.x vs 2.x and adapts behavior
- **Knox authentication** - Supports Bearer tokens, cookies, and passcode tokens for CDP deployments
- **Standalone NiFi authentication** - Direct username/password login or mTLS client certificates for local/on-prem NiFi with no Knox in front
- **Read-only by default** - Safe exploration of NiFi flows and configuration
- **Intelligent flow building** - Pattern recognition and requirements gathering for complex flows
- **24 read-only MCP tools** for exploring NiFi:
  - `get_nifi_version()` - Version and build information
  - `get_root_process_group()` - Root process group details
  - `list_processors(process_group_id)` - List processors in a process group
  - `list_connections(process_group_id)` - List connections in a process group
  - `get_bulletins(after_ms?)` - Recent bulletins and alerts
  - `list_parameter_contexts()` - Parameter contexts
  - `get_controller_services(process_group_id?)` - Controller services
  - `get_processor_types()` - Available processor types for flow building
  - `search_flow(query)` - Search for components in the flow
  - `get_connection_details(connection_id)` - Detailed connection information
  - `get_processor_details(processor_id)` - Detailed processor configuration
  - `list_input_ports(process_group_id)` - Input ports for a process group
  - `list_output_ports(process_group_id)` - Output ports for a process group
  - `get_processor_state(processor_id)` - Quick processor state check
  - `check_connection_queue(connection_id)` - Queue size (flowfiles + bytes)
  - `get_flow_summary(process_group_id)` - Flow statistics and health overview
  - `analyze_flow_build_request(user_request)` - Intelligent pattern recognition and requirements gathering
  - `get_parameter_context_details(context_id)` - Get parameter context with all parameters
  - `get_flow_health_status(process_group_id)` - Comprehensive flow health check (processors, services, connections, errors)
  - `find_controller_services_by_type(process_group_id, service_type)` - Search for existing controller services by type (prevents 409 conflicts)
  - `check_configuration()` - Validate current environment configuration
  - `get_setup_instructions()` - Interactive setup guidance for NiFi MCP Server
  - `get_best_practices_guide()` - Best practices for building NiFi flows
  - `get_recommended_workflow(flow_type)` - Step-by-step guidance for common flow patterns
- **42 write operations** (when `NIFI_READONLY=false`):
  - `start_processor(processor_id, version)` - Start a processor
  - `stop_processor(processor_id, version)` - Stop a processor
  - `create_processor(...)` - Create a new processor
  - `update_processor_config(...)` - Update processor configuration
  - `delete_processor(processor_id, version)` - Delete a processor
  - `create_connection(...)` - Connect components
  - `delete_connection(connection_id, version)` - Delete a connection
  - `empty_connection_queue(connection_id)` - Empty flowfiles from queue (⚠️ data loss)
  - `create_controller_service(pg_id, service_type, name)` - Create controller services (DBCPConnectionPool, RecordWriters, etc.)
  - `update_controller_service_properties(service_id, version, properties)` - Configure service properties
  - `get_controller_service_details(service_id)` - Get service configuration (read-only but listed here for context)
  - `delete_controller_service(service_id, version)` - Remove controller services
  - `enable_controller_service(service_id, version)` - Enable a controller service
  - `disable_controller_service(service_id, version)` - Disable a controller service
  - `create_process_group(parent_id, name, x, y)` - Create process groups (folders) for organizing flows
  - `update_process_group_name(pg_id, version, name)` - Rename process groups
  - `delete_process_group(pg_id, version)` - Remove empty process groups
  - `create_input_port(pg_id, name, x, y)` - Create input ports for inter-process-group communication
  - `create_output_port(pg_id, name, x, y)` - Create output ports for inter-process-group communication
  - `update_input_port(port_id, version, name)` - Rename input ports
  - `update_output_port(port_id, version, name)` - Rename output ports
  - `delete_input_port(port_id, version)` - Remove input ports
  - `delete_output_port(port_id, version)` - Remove output ports
  - `create_parameter_context(name, description, parameters)` - Create parameter contexts for environment-specific config
  - `update_parameter_context(context_id, version, ...)` - Update parameter contexts
  - `delete_parameter_context(context_id, version)` - Remove parameter contexts
  - `start_input_port(port_id, version)` - Start input port to enable data flow
  - `stop_input_port(port_id, version)` - Stop input port
  - `start_output_port(port_id, version)` - Start output port to enable data flow
  - `stop_output_port(port_id, version)` - Stop output port
  - `apply_parameter_context_to_process_group(pg_id, pg_version, context_id)` - Apply parameter context to enable #{param} usage
  - `start_all_processors_in_group(pg_id)` - Bulk start all processors at once (10-15x faster!)
  - `stop_all_processors_in_group(pg_id)` - Bulk stop all processors at once  
  - `enable_all_controller_services_in_group(pg_id)` - Bulk enable all services at once
  - `terminate_processor(processor_id, version)` - Force-terminate stuck processor (last resort)
  - `start_new_flow(flow_name, flow_description)` - Smart flow builder that automatically creates process groups and enforces best practices

## Quick Start

### For CDP NiFi deployments

Your NiFi API base URL will typically be:
```
https://<your-nifi-host>/nifi-2-dh/cdp-proxy/nifi-app/nifi-api
```

Get your Knox JWT token from the CDP UI and use it with the configurations below.

### For standalone / local NiFi deployments (no Knox)

Your NiFi API base URL will typically be:
```
https://<nifi-host>:8443/nifi-api
```

Point `NIFI_API_BASE` directly at your NiFi instance and skip Knox entirely. Choose one of:
- **Username/password** - set `NIFI_USERNAME` and `NIFI_PASSWORD` (works for NiFi's single-user provider or an LDAP/other login identity provider); the server logs in against NiFi's own `POST /access/token` endpoint.
- **mTLS client certificate** - set `NIFI_CLIENT_CERT` and `NIFI_CLIENT_KEY`; NiFi identifies you from the certificate, no login call needed.
- **Anonymous** - leave all auth variables unset if your NiFi instance has anonymous access enabled (e.g. a quick local/dev instance).

## Setup

### Option 1: Claude Desktop (Local)

1. **Clone and install:**
   ```bash
   git clone https://github.com/cloudera/nifi-mcp-server.git
   cd nifi-mcp-server
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

2. **Configure Claude Desktop** - Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:
   ```json
    {
      "mcpServers": {
        "nifi-mcp-server": {
          "command": "/FULL/PATH/TO/NiFi-MCP-Server/.venv/bin/python",
          "args": [
            "-m",
            "nifi_mcp_server.server"
          ],
          "env": {
            "MCP_TRANSPORT": "stdio",
            "NIFI_API_BASE": "https://nifi-2-dh-management0.yourshere.cloudera.site/nifi-2-dh/cdp-proxy/nifi-app/nifi-api",
            "KNOX_TOKEN": "<your_knox_bearer_token>",
            "NIFI_READONLY": "true"
          }
        }
      }
    }
   ```

3. **Restart Claude Desktop** and start asking questions about your NiFi flows!

**Example: standalone/local NiFi (no Knox), username/password login:**
```json
{
  "mcpServers": {
    "nifi-mcp-server": {
      "command": "/FULL/PATH/TO/NiFi-MCP-Server/.venv/bin/python",
      "args": [
        "-m",
        "nifi_mcp_server.server"
      ],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "NIFI_API_BASE": "https://localhost:8443/nifi-api",
        "NIFI_USERNAME": "admin",
        "NIFI_PASSWORD": "<your_nifi_password>",
        "KNOX_VERIFY_SSL": "false",
        "NIFI_READONLY": "true"
      }
    }
  }
}
```

**Example: standalone/local NiFi (no Knox), mTLS client certificate:**
```json
{
  "mcpServers": {
    "nifi-mcp-server": {
      "command": "/FULL/PATH/TO/NiFi-MCP-Server/.venv/bin/python",
      "args": [
        "-m",
        "nifi_mcp_server.server"
      ],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "NIFI_API_BASE": "https://localhost:8443/nifi-api",
        "NIFI_CLIENT_CERT": "/FULL/PATH/TO/client-cert.pem",
        "NIFI_CLIENT_KEY": "/FULL/PATH/TO/client-key.pem",
        "NIFI_READONLY": "true"
      }
    }
  }
}
```

> `KNOX_VERIFY_SSL=false` above is only needed for a local NiFi using a self-signed certificate; use `KNOX_CA_BUNDLE` to point at a CA bundle instead when possible.

### Option 2: Direct Installation (Cloudera Agent Studio)

For use with Cloudera Agent Studio, use the `uvx` command:

```json
{
  "mcpServers": {
    "nifi-mcp-server": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/cloudera/nifi-mcp-server@main",
        "run-server"
      ],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "NIFI_API_BASE": "https://nifi-2-dh-management0.yourshere.cloudera.site/nifi-2-dh/cdp-proxy/nifi-app/nifi-api",
        "KNOX_TOKEN": "<your_knox_bearer_token>",
        "NIFI_READONLY": "true"
      }
    }
  }
}
```

## Configuration Options

All configuration is done via environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `NIFI_API_BASE` | Yes* | Full NiFi API URL (e.g., `https://host/nifi-2-dh/cdp-proxy/nifi-app/nifi-api`, or `https://host:8443/nifi-api` for standalone NiFi) |
| `KNOX_GATEWAY_URL` | No | Knox gateway URL (alternative to `NIFI_API_BASE`) |

**Knox / CDP authentication** (any one of these; recommended when NiFi sits behind Knox):

| Variable | Description |
|----------|-------------|
| `KNOX_TOKEN` | Knox JWT token for authentication |
| `KNOX_COOKIE` | Alternative: provide full cookie string instead of token |
| `KNOX_USER` / `KNOX_PASSWORD` | Alternative: Knox basic-auth credentials, exchanged for a JWT |
| `KNOX_PASSCODE_TOKEN` | Alternative: Knox passcode token (auto-exchanged for JWT) |

**Standalone / local NiFi authentication** (no Knox in front; any one of these):

| Variable | Description |
|----------|-------------|
| `NIFI_USERNAME` / `NIFI_PASSWORD` | Logs in directly against NiFi's own `/access/token` endpoint (single-user or LDAP/other login identity provider) |
| `NIFI_CLIENT_CERT` / `NIFI_CLIENT_KEY` | Paths to a client certificate/key for mTLS auth directly against NiFi |

If none of the above are set, the server connects anonymously - fine for a local/dev NiFi with anonymous access enabled, otherwise NiFi will reject the requests.

**Other options:**

| Variable | Required | Description |
|----------|----------|-------------|
| `NIFI_READONLY` | No | Read-only mode (default: `true`) |
| `KNOX_VERIFY_SSL` | No | Verify SSL certificates (default: `true`) |
| `KNOX_CA_BUNDLE` | No | Path to CA certificate bundle |

\* Either `NIFI_API_BASE` or `KNOX_GATEWAY_URL` is required


For the NIFI_API_BASE, form using the url from Knox (less `-token`), and add the postfix `/nifi-app/nifi-api`
So, `https://nifi-2-dh-management0.yourdomain.cloudera.site/nifi-2-dh/cdp-proxy-token` becomes `https://nifi-2-dh-management0.yourdomain.cloudera.site/nifi-2-dh/cdp-proxy/nifi-app/nifi-api`

Get Knox Token from the Flow Management Datahub Knox instance:

![](/screenshots/knox-token-generation.png)


## Example Usage

### Read-Only Operations (Default)

Once configured, you can ask Claude questions like:

- "What version of NiFi am I running?"
- "List all processors in the root process group"
- "Show me recent bulletins"
- "What parameter contexts are configured?"
- "Tell me about the controller services"
- "What processor types are available for building flows?"
- "Search for processors containing 'kafka'"
- "Show me the details of connection abc-123"

### Write Operations (when NIFI_READONLY=false)

**⚠️ WARNING: Write operations modify your NiFi flows. Use with caution!**

To enable write operations, set `NIFI_READONLY=false` in your configuration. Then you can:

- **Build flows**: "Create a LogAttribute processor named 'MyLogger' in the root process group"
- **Manage processors**: "Start processor with ID abc-123", "Stop all processors in group xyz"
- **Connect components**: "Create a connection from processor A to processor B for the 'success' relationship"
- **Configure**: "Update the scheduling period of processor abc-123 to 30 seconds"
- **Control services**: "Enable the DBCPConnectionPool controller service"

**Examples:**
```
"Create a GenerateFlowFile processor in process group abc-123"
"Connect processor source-123 to processor dest-456 for success relationship"
"Start processor xyz-789"
"Check the queue status for connection conn-456"
"Empty the queue for connection conn-456 before deletion"  (⚠️ deletes flowfiles permanently)
"Delete connection conn-456"
```

**Important Notes:**
- **Version Tracking:** NiFi uses optimistic locking. Always fetch current versions before updates:
  ```python
  processor = get_processor_details(processor_id)
  current_version = processor['revision']['version']
  stop_processor(processor_id, current_version)
  ```
- **Queue Management:** Connections with flowfiles cannot be deleted. Use `get_connection_details()` to check queue status, then `empty_connection_queue()` if needed before deletion.


**Using the example `"List all processors in the root process group"`, we see the following for the example NiFi Canvas:**

![](/screenshots/nifi-canvas-1.png)

![](/screenshots/nifi-readcanvas-1.png)


**Using the example, `"What version of NiFi am I running?"`, we see the following:**

![](/screenshots/nifi-version-check.png)


## License

Apache License 2.0
