CREATE TABLE IF NOT EXISTS assistant_evidence_bundles (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  restaurant_id TEXT,
  conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id) ON DELETE CASCADE,
  assistant_message_id TEXT,
  bundle_type TEXT NOT NULL CHECK (bundle_type IN ('restaurant_locations', 'restaurant_update')),
  source_type TEXT NOT NULL,
  source_origin TEXT NOT NULL,
  raw_supplied_text TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'discarded')),
  idempotency_key TEXT NOT NULL,
  provider_metadata_json TEXT NOT NULL DEFAULT '{}',
  model TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (workspace_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS assistant_evidence_bundle_scope_idx
  ON assistant_evidence_bundles (workspace_id, status, updated_at);

CREATE TABLE IF NOT EXISTS assistant_evidence_items (
  id TEXT PRIMARY KEY,
  bundle_id TEXT NOT NULL REFERENCES assistant_evidence_bundles(id) ON DELETE CASCADE,
  workspace_id TEXT NOT NULL,
  entity_index INTEGER NOT NULL,
  field_name TEXT NOT NULL,
  raw_supplied_text TEXT,
  structured_value_json TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  confidence_basis TEXT NOT NULL,
  verification_status TEXT NOT NULL CHECK (verification_status IN ('verified_provider', 'stored_record', 'user_supplied', 'unverified_inference')),
  source_references_json TEXT NOT NULL DEFAULT '[]',
  provenance_chain_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS assistant_evidence_item_bundle_idx
  ON assistant_evidence_items (workspace_id, bundle_id, entity_index);
