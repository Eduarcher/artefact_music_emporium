-- Roles and databases for the prototype.
CREATE ROLE readonly LOGIN PASSWORD 'readonly';
CREATE DATABASE emporium_test OWNER emporium;

-- Read-only operational access for the MCP server (tables are created later
-- by the ingestion step; default privileges cover them).
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly;
GRANT USAGE ON SCHEMA public TO readonly;
