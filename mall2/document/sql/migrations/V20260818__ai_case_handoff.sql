-- Build 19: durable, privacy-minimal handoff from the customer diagnosis flow
-- to an independently authenticated operations role.
--
-- No raw customer message, order number, phone, address, token, RAG content,
-- or model prompt belongs in this record. Member linkage is Java-internal and
-- only exists to scope de-duplication.
CREATE TABLE IF NOT EXISTS `ai_case_handoff` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `case_id` char(36) NOT NULL COMMENT 'opaque UUID, safe for internal operations UI',
  `member_id` bigint(20) NOT NULL COMMENT 'Java-authenticated member, never exposed to operations AI',
  `case_key` char(64) NOT NULL COMMENT 'server-derived SHA-256 de-duplication key',
  `source_flow` varchar(32) NOT NULL COMMENT 'customer_diagnosis',
  `diagnosis_category` varchar(64) NOT NULL,
  `evidence_status` varchar(32) NOT NULL,
  `handoff_reason` varchar(64) NOT NULL,
  `requires_human_review` tinyint(1) NOT NULL DEFAULT 1,
  `case_status` varchar(32) NOT NULL DEFAULT 'OPEN',
  `schema_version` varchar(16) NOT NULL DEFAULT '1',
  `create_time` datetime NOT NULL,
  `update_time` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_case_handoff_case_id` (`case_id`),
  UNIQUE KEY `uk_ai_case_handoff_member_case_key` (`member_id`, `case_key`),
  KEY `idx_ai_case_handoff_status_time` (`case_status`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='Build19 privacy-minimal AI case handoff';
