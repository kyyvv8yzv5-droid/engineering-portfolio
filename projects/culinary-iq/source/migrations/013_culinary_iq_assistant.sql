CREATE TABLE IF NOT EXISTS assistant_conversations (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  title TEXT,
  selected_restaurant_id TEXT,
  selected_location_id TEXT,
  route_context TEXT,
  archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS assistant_conversation_scope_idx
  ON assistant_conversations (workspace_id, archived, updated_at);

CREATE TABLE IF NOT EXISTS assistant_messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id) ON DELETE CASCADE,
  workspace_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  selected_restaurant_id TEXT,
  selected_location_id TEXT,
  route_context TEXT,
  context_json TEXT NOT NULL DEFAULT '{}',
  tool_calls_json TEXT NOT NULL DEFAULT '[]',
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  navigation_json TEXT NOT NULL DEFAULT '[]',
  response_status TEXT NOT NULL,
  provider TEXT,
  model TEXT,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  correlation_id TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS assistant_message_history_idx
  ON assistant_messages (workspace_id, conversation_id, created_at);

CREATE TABLE IF NOT EXISTS assistant_tool_audit (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  message_id TEXT,
  correlation_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  argument_keys_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL,
  result_summary_json TEXT NOT NULL DEFAULT '{}',
  duration_ms INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS assistant_tool_audit_scope_idx
  ON assistant_tool_audit (workspace_id, conversation_id, created_at);
