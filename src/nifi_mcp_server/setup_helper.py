"""
Setup helper for guiding users through NiFi MCP Server configuration.

This module provides interactive setup guidance and validation for environment variables.
"""

from typing import Dict, List, Optional, Tuple
import os


class SetupGuide:
    """Interactive setup guide for NiFi MCP Server configuration."""
    
    @staticmethod
    def get_required_config() -> Dict[str, Dict[str, str]]:
        """Get required configuration with descriptions and examples."""
        return {
            "connection": {
                "NIFI_API_BASE": {
                    "description": "Full NiFi API base URL (required)",
                    "example": "https://nifi-host.com/nifi-2-dh/cdp-proxy/nifi-app/nifi-api",
                    "required": True
                }
            },
            "authentication": {
                "KNOX_TOKEN": {
                    "description": "Knox JWT Bearer token (recommended for CDP)",
                    "example": "eyJqa3UiOi...(long JWT token)",
                    "required": False
                },
                "KNOX_COOKIE": {
                    "description": "Knox authentication cookie (alternative)",
                    "example": "hadoop-jwt=eyJqa3UiOi...",
                    "required": False
                },
                "KNOX_USER": {
                    "description": "Knox username (for basic auth)",
                    "example": "admin",
                    "required": False
                },
                "KNOX_PASSWORD": {
                    "description": "Knox password (for basic auth)",
                    "example": "password123",
                    "required": False,
                    "sensitive": True
                }
            },
            "security": {
                "KNOX_VERIFY_SSL": {
                    "description": "Verify SSL certificates (true/false)",
                    "example": "true",
                    "default": "true",
                    "required": False
                }
            },
            "permissions": {
                "NIFI_READONLY": {
                    "description": "Read-only mode (true for safe exploration, false for modifications)",
                    "example": "false",
                    "default": "true",
                    "required": False
                }
            }
        }
    
    @staticmethod
    def validate_current_config() -> Tuple[bool, List[str], List[str]]:
        """
        Validate current environment configuration.
        
        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        errors = []
        warnings = []
        
        # Check required: NIFI_API_BASE
        nifi_api_base = os.getenv("NIFI_API_BASE")
        if not nifi_api_base:
            errors.append("❌ NIFI_API_BASE is required but not set")
            errors.append("   Example: export NIFI_API_BASE='https://nifi-host.com/nifi-api'")
        elif not nifi_api_base.startswith("http"):
            errors.append("❌ NIFI_API_BASE must start with 'http://' or 'https://'")
        
        # Check authentication (at least one method - Knox/CDP, or standalone/local NiFi)
        knox_token = os.getenv("KNOX_TOKEN")
        knox_cookie = os.getenv("KNOX_COOKIE")
        knox_user = os.getenv("KNOX_USER")
        knox_password = os.getenv("KNOX_PASSWORD")
        knox_passcode_token = os.getenv("KNOX_PASSCODE_TOKEN")

        nifi_username = os.getenv("NIFI_USERNAME")
        nifi_password = os.getenv("NIFI_PASSWORD")
        nifi_client_cert = os.getenv("NIFI_CLIENT_CERT")
        nifi_client_key = os.getenv("NIFI_CLIENT_KEY")

        has_knox_auth = any([knox_token, knox_cookie, (knox_user and knox_password), knox_passcode_token])
        has_local_nifi_auth = any([(nifi_username and nifi_password), (nifi_client_cert and nifi_client_key)])
        has_auth = has_knox_auth or has_local_nifi_auth

        if not has_auth:
            # Neither Knox/CDP nor standalone-NiFi credentials are set. This is expected
            # (and fine) when NiFi is running with anonymous access enabled, e.g. a local
            # single-user dev instance - so this is informational, not a problem to fix.
            warnings.append("⚠️  No authentication configured - requests will be sent anonymously")
            warnings.append("   This is fine for local/dev NiFi with anonymous access enabled.")
            warnings.append("   Otherwise, set ONE of:")
            warnings.append("     - KNOX_TOKEN / KNOX_COOKIE / KNOX_USER+KNOX_PASSWORD (Knox / CDP)")
            warnings.append("     - NIFI_USERNAME+NIFI_PASSWORD (standalone NiFi login)")
            warnings.append("     - NIFI_CLIENT_CERT+NIFI_CLIENT_KEY (standalone NiFi mTLS)")
        
        # Check SSL verification
        verify_ssl = os.getenv("KNOX_VERIFY_SSL", "true").lower()
        if verify_ssl == "false":
            warnings.append("⚠️  SSL verification disabled (KNOX_VERIFY_SSL=false)")
            warnings.append("   This is insecure for production use")
        
        # Check readonly mode
        readonly = os.getenv("NIFI_READONLY", "true").lower()
        if readonly == "false":
            warnings.append("⚠️  Write operations enabled (NIFI_READONLY=false)")
            warnings.append("   Be careful - you can modify flows!")
        
        is_valid = len(errors) == 0
        return is_valid, errors, warnings
    
    @staticmethod
    def get_setup_instructions() -> str:
        """Get comprehensive setup instructions."""
        return """
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║                     NiFi MCP Server - Setup Guide                            ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

📋 REQUIRED CONFIGURATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. NiFi API Base URL (REQUIRED)
   
   For CDP NiFi:
   export NIFI_API_BASE="https://<nifi-host>/nifi-2-dh/cdp-proxy/nifi-app/nifi-api"
   
   For standalone NiFi:
   export NIFI_API_BASE="https://<nifi-host>:8443/nifi-api"

2. Authentication (Choose ONE method)
   
   Option A - Knox JWT Token (Recommended for CDP):
   export KNOX_TOKEN="eyJqa3UiOi..."
   
   Option B - Knox Cookie:
   export KNOX_COOKIE="hadoop-jwt=eyJqa3UiOi..."
   
   Option C - Basic Auth:
   export KNOX_USER="your_username"
   export KNOX_PASSWORD="your_password"

   -- OR, for standalone NiFi with no Knox in front --

   Option D - Standalone NiFi login (single-user or LDAP):
   export NIFI_USERNAME="your_username"
   export NIFI_PASSWORD="your_password"

   Option E - Standalone NiFi mTLS:
   export NIFI_CLIENT_CERT="/path/to/client-cert.pem"
   export NIFI_CLIENT_KEY="/path/to/client-key.pem"

   -- OR leave authentication unset for a NiFi instance with anonymous access enabled --

3. Permissions (Optional)
   
   For read-only mode (safe exploration):
   export NIFI_READONLY="true"  # Default
   
   For write operations (flow building):
   export NIFI_READONLY="false"

🔒 SECURITY OPTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SSL Verification (production):
export KNOX_VERIFY_SSL="true"  # Default

SSL Verification (dev/test with self-signed certs):
export KNOX_VERIFY_SSL="false"

Custom CA Bundle:
export KNOX_CA_BUNDLE="/path/to/ca-bundle.crt"

⚡ QUICK START FOR CDP NIFI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 1. Set your NiFi URL
export NIFI_API_BASE="https://nifi-2-dh-management0.my-cluster.com/nifi-2-dh/cdp-proxy/nifi-app/nifi-api"

# 2. Set your Knox token
export KNOX_TOKEN="eyJqa3UiOi..."

# 3. Enable write operations (for building flows)
export NIFI_READONLY="false"

# 4. Verify configuration
python -c "from nifi_mcp_server.setup_helper import SetupGuide; SetupGuide.check_and_report()"

⚡ QUICK START FOR LOCAL / STANDALONE NIFI (NO KNOX)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 1. Set your NiFi URL
export NIFI_API_BASE="https://localhost:8443/nifi-api"

# 2a. Login with username/password (single-user or LDAP NiFi)
export NIFI_USERNAME="admin"
export NIFI_PASSWORD="your_password"

#   -- OR 2b. mTLS with a client certificate --
# export NIFI_CLIENT_CERT="/path/to/client-cert.pem"
# export NIFI_CLIENT_KEY="/path/to/client-key.pem"

#   -- OR 2c. leave both unset if NiFi has anonymous access enabled --

# 3. Enable write operations (for building flows)
export NIFI_READONLY="false"

# 4. Verify configuration
python -c "from nifi_mcp_server.setup_helper import SetupGuide; SetupGuide.check_and_report()"

✅ VERIFICATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run this command to verify your configuration:
python -c "from nifi_mcp_server.setup_helper import SetupGuide; SetupGuide.check_and_report()"

"""
    
    @staticmethod
    def check_and_report() -> bool:
        """
        Check configuration and print detailed report.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        print("\n🔍 Checking NiFi MCP Server Configuration...\n")
        
        is_valid, errors, warnings = SetupGuide.validate_current_config()
        
        if errors:
            print("❌ CONFIGURATION ERRORS:\n")
            for error in errors:
                print(f"  {error}")
            print()
        
        if warnings:
            print("⚠️  CONFIGURATION WARNINGS:\n")
            for warning in warnings:
                print(f"  {warning}")
            print()
        
        if is_valid and not warnings:
            print("✅ Configuration is valid!\n")
            print("📝 Current configuration:")
            print(f"   NIFI_API_BASE: {os.getenv('NIFI_API_BASE')}")
            print(f"   NIFI_READONLY: {os.getenv('NIFI_READONLY', 'true')}")
            
            if os.getenv("KNOX_TOKEN"):
                print(f"   Authentication: Knox JWT Token (configured)")
            elif os.getenv("KNOX_COOKIE"):
                print(f"   Authentication: Knox Cookie (configured)")
            elif os.getenv("KNOX_USER"):
                print(f"   Authentication: Knox Basic Auth (user: {os.getenv('KNOX_USER')})")
            elif os.getenv("NIFI_CLIENT_CERT"):
                print(f"   Authentication: Standalone NiFi mTLS (configured)")
            elif os.getenv("NIFI_USERNAME"):
                print(f"   Authentication: Standalone NiFi login (user: {os.getenv('NIFI_USERNAME')})")
            else:
                print(f"   Authentication: None (anonymous)")
            print()
        elif is_valid:
            print("✅ Configuration is valid (with warnings)\n")
        else:
            print("❌ Configuration is INVALID\n")
            print("📖 For setup instructions, run:")
            print("   python -c \"from nifi_mcp_server.setup_helper import SetupGuide; print(SetupGuide.get_setup_instructions())\"")
            print()
        
        return is_valid
    
    @staticmethod
    def get_missing_config_message() -> str:
        """Get user-friendly message for missing configuration."""
        return """
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║                  ⚠️  NiFi MCP Server Not Configured                          ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

The NiFi MCP Server requires configuration before use.

📋 MINIMUM REQUIRED:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Set your NiFi API base URL:
   export NIFI_API_BASE="https://<your-nifi-host>/nifi-api"

2. Set authentication (Knox token recommended for CDP):
   export KNOX_TOKEN="<your-jwt-token>"

3. Enable write operations (if you want to build flows):
   export NIFI_READONLY="false"

💡 QUICK EXAMPLE FOR CDP NIFI:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export NIFI_API_BASE="https://nifi-2-dh-management0.my-cluster.com/nifi-2-dh/cdp-proxy/nifi-app/nifi-api"
export KNOX_TOKEN="eyJqa3UiOi..."
export NIFI_READONLY="false"

📖 For detailed setup instructions:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run: python -c "from nifi_mcp_server.setup_helper import SetupGuide; print(SetupGuide.get_setup_instructions())"

Or check the README.md file in the project root.

"""


def validate_config_or_exit():
    """Validate configuration and exit with helpful message if invalid."""
    is_valid, errors, warnings = SetupGuide.validate_current_config()
    
    if not is_valid:
        print(SetupGuide.get_missing_config_message())
        import sys
        sys.exit(1)
    
    if warnings:
        print("⚠️  Configuration warnings detected:")
        for warning in warnings:
            print(f"  {warning}")
        print()


def get_jdbc_driver_troubleshooting() -> str:
    """Get troubleshooting guide for JDBC driver issues."""
    return """
╔══════════════════════════════════════════════════════════════════════════════╗
║           JDBC Driver Requirement for Database Connections                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

Common Error:
  "Driver class com.mysql.cj.jdbc.Driver is not found"
  "ClassNotFoundException: [database].jdbc.Driver"

Root Cause:
  NiFi does not include JDBC drivers by default. They must be installed by your
  NiFi administrator on the NiFi server(s).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  IMPORTANT: This MCP server cannot install JDBC drivers remotely.

JDBC drivers must be installed on the NiFi server by an administrator with
server access. This typically involves:

1. Downloading the appropriate JDBC driver JAR file
2. Copying it to NiFi's lib directory
3. Restarting NiFi

Contact your NiFi administrator to:
  - Install the required JDBC driver for your database
  - Confirm which databases are already supported
  - Get the correct driver class name to use

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COMMON JDBC DRIVERS NEEDED:

  MySQL/MariaDB:
    Driver Class: com.mysql.cj.jdbc.Driver
    JAR: mysql-connector-j-8.3.0.jar
  
  PostgreSQL:
    Driver Class: org.postgresql.Driver
    JAR: postgresql-42.x.x.jar
  
  Oracle:
    Driver Class: oracle.jdbc.OracleDriver
    JAR: ojdbc8.jar (or ojdbc11.jar)
  
  SQL Server:
    Driver Class: com.microsoft.sqlserver.jdbc.SQLServerDriver
    JAR: mssql-jdbc-12.x.x.jar

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ALTERNATIVE: Use CDC Processors (No JDBC Driver Needed!)

For real-time data capture, consider using NiFi's CDC processors which don't
require JDBC drivers:

  - MySQL: CaptureChangeMySQL (uses binlog protocol)
  - MongoDB: CaptureChangeMongoDB
  - SQL Server: Use Debezium connectors

These are often more efficient than JDBC-based approaches.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Once drivers are installed by your administrator, you can use this MCP server to:
  ✅ Create and configure DBCPConnectionPool controller services
  ✅ Build complete database integration flows
  ✅ Manage all NiFi operations remotely
"""

