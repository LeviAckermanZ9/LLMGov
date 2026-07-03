-- ClickHouse initialization: llm_audit_logs table
-- Schema from LLMGov Master Specification Section 6

CREATE TABLE IF NOT EXISTS default.llm_audit_logs (
    trace_id          UUID,
    timestamp         DateTime64(3),
    sanitized_prompt  String,
    raw_response      String,
    has_pii_redacted  UInt8,
    toxicity_score    Float32,
    jailbreak_score   Float32,
    prev_hash         String,
    row_hash          String
) ENGINE = MergeTree()
ORDER BY (timestamp);
