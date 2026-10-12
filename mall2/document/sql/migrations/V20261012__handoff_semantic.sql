-- Additive semantic projections and human-reviewed groups. No historic backfill.
CREATE TABLE IF NOT EXISTS ai_handoff_summary (
 case_ref char(36) NOT NULL PRIMARY KEY, input_hash char(64) NOT NULL,
 snapshot_json text NULL, input_version int NOT NULL DEFAULT 1,
 state varchar(32) NOT NULL, attempts int NOT NULL DEFAULT 0,
 lease_ref char(36) NULL, lease_until datetime NULL, summary_json text NULL,
 summary_version int NOT NULL DEFAULT 0, model_version varchar(96) NULL,
 prompt_version varchar(32) NOT NULL DEFAULT 'handoff-summary-v1',
 review_state varchar(24) NOT NULL DEFAULT 'AI_UNREVIEWED',
 error_code varchar(48) NULL, created_at datetime NOT NULL, updated_at datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_summary_audit (
 case_ref char(36) NOT NULL, version int NOT NULL, source varchar(24) NOT NULL,
 actor_ref varchar(64) NOT NULL, input_hash char(64) NOT NULL, created_at datetime NOT NULL,
 PRIMARY KEY(case_ref,version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_problem (
 case_ref char(36) NOT NULL PRIMARY KEY, version int NOT NULL DEFAULT 1,
 projection_json text NOT NULL, projection_hash char(64) NOT NULL,
 quality varchar(32) NOT NULL, created_at datetime NOT NULL,
 deleted_at datetime NULL, index_state varchar(24) NOT NULL,
 attempts int NOT NULL DEFAULT 0, lease_ref char(36) NULL, lease_until datetime NULL,
 embedding_version varchar(96) NULL, template_version varchar(32) NOT NULL,
 KEY idx_problem_work(index_state,lease_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_problem_group (
 group_ref char(36) NOT NULL PRIMARY KEY, title varchar(120) NOT NULL,
 topic varchar(32) NOT NULL, taxonomy varchar(24) NOT NULL DEFAULT 'issues-v1',
 version int NOT NULL DEFAULT 1, actor_ref varchar(64) NOT NULL,
 created_at datetime NOT NULL, updated_at datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_problem_member (
 case_ref char(36) NOT NULL, taxonomy varchar(24) NOT NULL DEFAULT 'issues-v1',
 group_ref char(36) NOT NULL, projection_version int NOT NULL,
 basis varchar(48) NOT NULL, actor_ref varchar(64) NOT NULL, created_at datetime NOT NULL,
 PRIMARY KEY(case_ref,taxonomy), KEY idx_problem_group(group_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_semantic_audit (
 request_ref char(36) NOT NULL PRIMARY KEY, payload_hash char(64) NOT NULL,
 group_ref char(36) NULL, case_ref char(36) NULL, action varchar(32) NOT NULL,
 actor_ref varchar(64) NOT NULL, created_at datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_group_analysis (
 analysis_ref char(36) NOT NULL PRIMARY KEY, group_ref char(36) NOT NULL,
 group_version int NOT NULL, snapshot_json mediumtext NULL, snapshot_hash char(64) NOT NULL,
 state varchar(24) NOT NULL, attempts int NOT NULL DEFAULT 0,
 lease_ref char(36) NULL, lease_until datetime NULL, result_json text NULL,
 model_version varchar(96) NULL, actor_ref varchar(64) NOT NULL,
 reviewed_by varchar(64) NULL, created_at datetime NOT NULL,
 KEY idx_group_analysis(group_ref,state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_improvement_evidence (
 improvement_ref char(36) NOT NULL PRIMARY KEY, group_ref char(36) NOT NULL,
 group_version int NOT NULL, analysis_ref char(36) NULL,
 verification_method varchar(48) NOT NULL, evidence_ref varchar(160) NOT NULL,
 actor_ref varchar(64) NOT NULL, created_at datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_handoff_analysis_source (
 analysis_ref char(36) NOT NULL, case_ref char(36) NOT NULL,
 PRIMARY KEY(analysis_ref,case_ref), KEY idx_analysis_source(case_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
