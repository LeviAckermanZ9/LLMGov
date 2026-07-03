-- ClickHouse initialization: llm_eval_results table
-- Schema from LLMGov Master Specification Section 6

CREATE TABLE IF NOT EXISTS default.llm_eval_results (
    trace_id        UUID,
    timestamp       DateTime64(3),
    schema_valid    UInt8,
    judge_score     Float32,
    judge_rationale String,
    hand_labeled    UInt8
) ENGINE = MergeTree()
ORDER BY (timestamp);
