"""Chainlit thread-persistence schema.

Chainlit's SQLAlchemy data layer expects these tables to exist but does not
create them. They live in the same Postgres database as the rest of the
prototype so sessions can be listed and resumed from the sidebar. Each entry is
a single statement so it can be executed individually with asyncpg.
"""

CHAINLIT_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS users (
        "id" UUID PRIMARY KEY,
        "identifier" TEXT NOT NULL UNIQUE,
        "metadata" JSONB NOT NULL,
        "createdAt" TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS threads (
        "id" UUID PRIMARY KEY,
        "createdAt" TEXT,
        "name" TEXT,
        "userId" UUID,
        "userIdentifier" TEXT,
        "tags" TEXT[],
        "metadata" JSONB,
        FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS steps (
        "id" UUID PRIMARY KEY,
        "name" TEXT NOT NULL,
        "type" TEXT NOT NULL,
        "threadId" UUID NOT NULL,
        "parentId" UUID,
        "streaming" BOOLEAN NOT NULL,
        "waitForAnswer" BOOLEAN,
        "isError" BOOLEAN,
        "metadata" JSONB,
        "tags" TEXT[],
        "input" TEXT,
        "output" TEXT,
        "createdAt" TEXT,
        "command" TEXT,
        "start" TEXT,
        "end" TEXT,
        "generation" JSONB,
        "showInput" TEXT,
        "language" TEXT,
        "indent" INT,
        "defaultOpen" BOOLEAN,
        "autoCollapse" BOOLEAN,
        "modes" JSONB,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    )
    """,
    """
    ALTER TABLE steps ADD COLUMN IF NOT EXISTS "autoCollapse" BOOLEAN
    """,
    """
    CREATE TABLE IF NOT EXISTS elements (
        "id" UUID PRIMARY KEY,
        "threadId" UUID,
        "type" TEXT,
        "url" TEXT,
        "chainlitKey" TEXT,
        "name" TEXT NOT NULL,
        "display" TEXT,
        "objectKey" TEXT,
        "size" TEXT,
        "page" INT,
        "language" TEXT,
        "forId" UUID,
        "mime" TEXT,
        "props" JSONB,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feedbacks (
        "id" UUID PRIMARY KEY,
        "forId" UUID NOT NULL,
        "threadId" UUID NOT NULL,
        "value" INT NOT NULL,
        "comment" TEXT,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    )
    """,
)
