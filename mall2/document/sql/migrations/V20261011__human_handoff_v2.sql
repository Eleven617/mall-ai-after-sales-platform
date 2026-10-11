-- Additive handoff projections. Existing cases and audits remain authoritative.
CREATE TABLE IF NOT EXISTS ai_handoff_context (
 case_ref char(36) NOT NULL, plan_version int NOT NULL,
 completed_steps int NOT NULL, verified_evidence_count int NOT NULL,
 PRIMARY KEY(case_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_request (
 member_id bigint NOT NULL, request_ref char(64) NOT NULL, content_hash char(64) NOT NULL,
 case_ref char(36) NOT NULL, PRIMARY KEY(member_id,request_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_analysis_provenance (
 case_ref char(36) NOT NULL, lease_ref char(36) NOT NULL,
 input_hash char(64) NOT NULL, taxonomy_version varchar(24) NOT NULL,
 prompt_version varchar(24) NOT NULL, model_version varchar(80) NOT NULL,
 created_at datetime NOT NULL, PRIMARY KEY(case_ref,lease_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_retention_hold (
 case_ref char(36) NOT NULL, held tinyint NOT NULL DEFAULT 0,
 actor_ref varchar(64) NOT NULL, updated_at datetime NOT NULL,
 PRIMARY KEY(case_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_retention_audit (
 audit_ref char(36) NOT NULL, actor_ref varchar(64) NOT NULL,
 projection_days int NOT NULL, event_days int NOT NULL,
 projections_cleared int NOT NULL, events_removed int NOT NULL,
 created_at datetime NOT NULL, PRIMARY KEY(audit_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_scope (
 member_id bigint NOT NULL, scope_key char(64) NOT NULL, case_ref char(36) NULL,
 PRIMARY KEY(member_id, scope_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_record (
 case_ref char(36) NOT NULL, member_id bigint NOT NULL, request_ref char(64) NOT NULL,
 scope_key char(64) NOT NULL, content_hash char(64) NOT NULL,
 trigger_source varchar(40) NOT NULL, entry_channel varchar(16) NOT NULL,
 business_topic varchar(32) NOT NULL, customer_reason varchar(48) NOT NULL,
 task_ref varchar(80) NULL, stage varchar(40) NOT NULL,
 snapshot_version int NOT NULL DEFAULT 1, confirmed_at datetime NOT NULL,
 verified_reason varchar(48) NULL, review_version int NOT NULL DEFAULT 0,
 reviewed_at datetime NULL, reviewer_ref varchar(64) NULL,
 analysis_state varchar(20) NOT NULL DEFAULT 'PENDING', analysis_attempts int NOT NULL DEFAULT 0,
 analysis_lease char(36) NULL, lease_until datetime NULL, model_reason varchar(48) NULL,
 analysis_version varchar(24) NULL, projection_cleared tinyint NOT NULL DEFAULT 0,
 PRIMARY KEY(case_ref), UNIQUE KEY uk_handoff_request(member_id,request_ref),
 KEY idx_handoff_window(confirmed_at,business_topic,trigger_source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_event (
 event_ref char(64) NOT NULL, member_id bigint NOT NULL, request_ref char(64) NOT NULL,
 case_ref char(36) NULL, event_type varchar(24) NOT NULL, created_at datetime NOT NULL,
 PRIMARY KEY(event_ref), KEY idx_handoff_event_window(created_at,event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_analysis (
 case_ref char(36) NOT NULL, revision int NOT NULL, actor_ref varchar(64) NOT NULL,
 source varchar(16) NOT NULL, reason varchar(48) NOT NULL, created_at datetime NOT NULL,
 PRIMARY KEY(case_ref,source,revision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_operations_improvement (
 improvement_ref char(36) NOT NULL, case_ref char(36) NOT NULL,
 reason varchar(48) NOT NULL, team varchar(24) NOT NULL, state varchar(24) NOT NULL,
 version int NOT NULL, verification_code varchar(40) NOT NULL,
 actor_ref varchar(64) NOT NULL, created_at datetime NOT NULL, updated_at datetime NOT NULL,
 PRIMARY KEY(improvement_ref), KEY idx_improvement_state(state,updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_operations_improvement_audit (
 improvement_ref char(36) NOT NULL, version int NOT NULL, state varchar(24) NOT NULL,
 verification_code varchar(40) NOT NULL, actor_ref varchar(64) NOT NULL, created_at datetime NOT NULL,
 PRIMARY KEY(improvement_ref,version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
