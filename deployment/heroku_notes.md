# Heroku deployment — not implemented

Procfile and runtime.txt are structural placeholders, not valid deployment configuration.
Do not deploy them. Choose a supported runtime and configure the real web process once
mcp_server/server.py is implemented. Verify the required root-level Heroku configuration
before deployment; these nested files are not automatically a working app setup.

SCC performs batch processing; Heroku stores knowledge in Postgres with pgvector and
serves authenticated MCP retrieval. Confirm database/vector support, connectivity,
HTTP transport, authentication, authorization, and embedding model compatibility.
Supply credentials through approved environment variables or secret management.
Heroku hosting alone does not restrict access to Salesforce users.
