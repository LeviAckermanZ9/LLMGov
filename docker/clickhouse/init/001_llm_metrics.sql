-- ClickHouse initialization: llm_metrics table
-- Schema from LLMGov Master Specification Section 6

CREATE TABLE IF NOT EXISTS default.llm_metrics (
    trace_id          UUID,
    timestamp         DateTime64(3),
    app_id            String,
    prompt_version    String,
    model_requested   String,
    model_used        String,
    provider          String,
    ttft_ms           Float32,
    total_duration_ms Float32,
    prompt_tokens     UInt32,
    completion_tokens UInt32,
    calculated_cost   Float64,
    status_code       UInt16
) ENGINE = MergeTree()
ORDER BY (app_id, provider, model_used, timestamp);
