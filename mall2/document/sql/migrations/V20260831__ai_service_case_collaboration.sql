-- Final-upgrade FR-19: deterministic human service-case collaboration.
--
-- This migration stores only the minimal handoff/category/state needed to
-- route and process a complex AI case. It does NOT copy raw customer chat,
-- JWTs, addresses, payment data, RAG passages, prompts or tool payloads.

CREATE TABLE IF NOT EXISTS `ai_service_case_routing_rule` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `diagnosis_category` varchar(64) NOT NULL,
  `priority` varchar(16) NOT NULL DEFAULT 'normal',
  `eligible_queue_ref` varchar(64) NOT NULL,
  `required_facts` varchar(128) NOT NULL,
  `policy_version` varchar(32) NOT NULL DEFAULT 'v1',
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `create_time` datetime NOT NULL,
  `update_time` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_service_case_route_category_version` (`diagnosis_category`,`policy_version`),
  KEY `idx_service_case_route_active` (`active`,`diagnosis_category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI handoff deterministic routing allow-list';

INSERT IGNORE INTO `ai_service_case_routing_rule`
  (`diagnosis_category`,`priority`,`eligible_queue_ref`,`required_facts`,`policy_version`,`active`,`create_time`,`update_time`)
VALUES
  ('delivery_exception','high','logistics_review','order_and_logistics','v1',1,NOW(),NOW()),
  ('policy_insufficient','normal','policy_review','policy_evidence','v1',1,NOW(),NOW()),
  ('tool_failure','normal','general_after_sales','verified_fact_reference','v1',1,NOW(),NOW()),
  ('facts_incomplete','normal','general_after_sales','identifier_or_fact','v1',1,NOW(),NOW()),
  ('needs_order_identifier','low','general_after_sales','identifier','v1',1,NOW(),NOW()),
  ('order_state_review','normal','general_after_sales','order_fact','v1',1,NOW(),NOW()),
  ('delivery_in_transit','low','logistics_review','logistics_fact','v1',1,NOW(),NOW());

CREATE TABLE IF NOT EXISTS `ai_service_case` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `case_id` char(36) NOT NULL,
  `member_id` bigint(20) NOT NULL COMMENT 'Java internal ownership only',
  `case_key` char(64) NOT NULL COMMENT 'server-derived handoff de-duplication key',
  `queue_ref` varchar(64) NOT NULL,
  `diagnosis_category` varchar(64) NOT NULL,
  `priority` varchar(16) NOT NULL,
  `state` varchar(48) NOT NULL,
  `state_version` int(11) NOT NULL DEFAULT 1,
  `assignee_ref` varchar(64) DEFAULT NULL,
  `public_status` varchar(160) NOT NULL,
  `customer_information_type` varchar(48) DEFAULT NULL,
  `customer_information` varchar(240) DEFAULT NULL,
  `last_public_message` varchar(500) DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_service_case_id` (`case_id`),
  UNIQUE KEY `uk_service_case_member_key` (`member_id`,`case_key`),
  KEY `idx_service_case_queue_state` (`queue_ref`,`state`,`updated_at`),
  KEY `idx_service_case_assignee_state` (`assignee_ref`,`state`,`updated_at`),
  KEY `idx_service_case_member` (`member_id`,`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='minimal human-collaboration service cases';

CREATE TABLE IF NOT EXISTS `ai_service_case_action` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `action_id` char(36) NOT NULL,
  `case_id` char(36) NOT NULL,
  `actor_kind` varchar(24) NOT NULL,
  `actor_ref` varchar(64) NOT NULL,
  `action_type` varchar(48) NOT NULL,
  `expected_version` int(11) NOT NULL,
  `result_code` varchar(48) NOT NULL,
  `public_message` varchar(500) DEFAULT NULL,
  `internal_note` varchar(500) DEFAULT NULL,
  `idempotency_key` char(32) NOT NULL,
  `correlation_ref` varchar(64) DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_service_case_action_id` (`action_id`),
  UNIQUE KEY `uk_service_case_actor_idempotency` (`case_id`,`actor_kind`,`actor_ref`,`idempotency_key`),
  KEY `idx_service_case_action_case` (`case_id`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='auditable idempotent human/customer case actions';

CREATE TABLE IF NOT EXISTS `ai_service_case_outbox` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `event_id` char(36) NOT NULL,
  `case_id` char(36) NOT NULL,
  `member_id` bigint(20) NOT NULL,
  `event_type` varchar(96) NOT NULL,
  `state_version` int(11) NOT NULL,
  `correlation_ref` varchar(64) DEFAULT NULL,
  `status` varchar(24) NOT NULL DEFAULT 'PENDING',
  `attempt_count` int(11) NOT NULL DEFAULT 0,
  `available_at` datetime DEFAULT NULL,
  `lease_until` datetime DEFAULT NULL,
  `published_at` datetime DEFAULT NULL,
  `last_error` varchar(500) DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_service_case_outbox_event` (`event_id`),
  KEY `idx_service_case_outbox_ready` (`status`,`available_at`,`lease_until`),
  KEY `idx_service_case_outbox_case` (`case_id`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='transactional events for human service-case state';

CREATE TABLE IF NOT EXISTS `ai_service_case_event_delivery` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `event_id` char(36) NOT NULL,
  `case_id` char(36) NOT NULL,
  `delivery_status` varchar(24) NOT NULL,
  `received_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_service_case_delivery_event` (`event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='idempotent RabbitMQ service-case deliveries';

-- Dedicated processor identity is intentionally separate from the existing
-- read-only operations-analysis and developer-quality roles.
INSERT INTO ums_role (name, description, admin_count, create_time, status, sort)
SELECT '售后处理人员', '只能领取和处理最小化 AI 转人工案件', 0, NOW(), 1, 0
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM ums_role WHERE name = '售后处理人员');

INSERT INTO ums_admin (username, password, icon, email, nick_name, note, create_time, login_time, status)
SELECT
  'afterSalesProcessor',
  '$2b$12$2bNOx6X4CUnd4Q7jHBLg9.kR79XZkr1HZ8fWbKOQYocJDNFB6kOcq',
  NULL, NULL, '售后处理人员', '本地合成人工协同演示专用账号', NOW(), NULL, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM ums_admin WHERE username = 'afterSalesProcessor');

INSERT INTO ums_admin_role_relation (admin_id, role_id)
SELECT admin.id, role.id
FROM ums_admin AS admin
JOIN ums_role AS role ON role.name = '售后处理人员'
WHERE admin.username = 'afterSalesProcessor'
  AND NOT EXISTS (
    SELECT 1 FROM ums_admin_role_relation AS relation_record
    WHERE relation_record.admin_id = admin.id AND relation_record.role_id = role.id
  );
