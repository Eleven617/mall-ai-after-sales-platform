-- Build 19.2 local-only demonstration records for the read-only handoff
-- overview. They contain no order, return, Outbox, message, token or PII.
-- They are intentionally inserted as durable CaseHandoff-shaped records so
-- the 7/30 day aggregate queries are real SQL results, not hard-coded UI data.
-- Existing records are never updated or removed.

INSERT INTO ai_case_handoff (
    case_id, member_id, case_key, source_flow, diagnosis_category,
    evidence_status, handoff_reason, requires_human_review, case_status,
    schema_version, create_time, update_time
)
SELECT
    '19200001-0000-4000-8000-000000000001', 1,
    SHA2('build19-2-local-demo-delivery-exception', 256), 'customer_diagnosis',
    'delivery_exception', 'partial', 'manual_review', 1, 'OPEN', '1',
    DATE_SUB(NOW(), INTERVAL 2 DAY), DATE_SUB(NOW(), INTERVAL 2 DAY)
WHERE NOT EXISTS (
    SELECT 1 FROM ai_case_handoff
    WHERE case_id = '19200001-0000-4000-8000-000000000001'
);

INSERT INTO ai_case_handoff (
    case_id, member_id, case_key, source_flow, diagnosis_category,
    evidence_status, handoff_reason, requires_human_review, case_status,
    schema_version, create_time, update_time
)
SELECT
    '19200002-0000-4000-8000-000000000002', 1,
    SHA2('build19-2-local-demo-policy-gap', 256), 'customer_diagnosis',
    'policy_insufficient', 'insufficient', 'insufficient_evidence', 1, 'OPEN', '1',
    DATE_SUB(NOW(), INTERVAL 12 DAY), DATE_SUB(NOW(), INTERVAL 12 DAY)
WHERE NOT EXISTS (
    SELECT 1 FROM ai_case_handoff
    WHERE case_id = '19200002-0000-4000-8000-000000000002'
);

INSERT INTO ai_case_handoff (
    case_id, member_id, case_key, source_flow, diagnosis_category,
    evidence_status, handoff_reason, requires_human_review, case_status,
    schema_version, create_time, update_time
)
SELECT
    '19200003-0000-4000-8000-000000000003', 1,
    SHA2('build19-2-local-demo-facts-incomplete', 256), 'customer_diagnosis',
    'facts_incomplete', 'partial', 'manual_review', 1, 'OPEN', '1',
    DATE_SUB(NOW(), INTERVAL 22 DAY), DATE_SUB(NOW(), INTERVAL 22 DAY)
WHERE NOT EXISTS (
    SELECT 1 FROM ai_case_handoff
    WHERE case_id = '19200003-0000-4000-8000-000000000003'
);
