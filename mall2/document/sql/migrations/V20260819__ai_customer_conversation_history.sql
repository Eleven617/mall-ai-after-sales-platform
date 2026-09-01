-- Build 19.1: member-scoped customer conversation history.
--
-- The conversation list deliberately stores only a server-approved generic
-- title. Raw messages are visible only after the authenticated owner opens a
-- conversation through the Java-owned authorization boundary.
CREATE TABLE IF NOT EXISTS `ai_customer_conversation` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `conversation_id` char(36) NOT NULL COMMENT 'opaque UUID shown only to its owner',
  `member_id` bigint(20) NOT NULL COMMENT 'current Java-authenticated member',
  `title` varchar(64) NOT NULL COMMENT 'allow-listed, non-sensitive customer title',
  `create_time` datetime NOT NULL,
  `update_time` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_customer_conversation_id` (`conversation_id`),
  KEY `idx_ai_customer_conversation_member_updated` (`member_id`, `update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Build19.1 member-scoped AI conversation history';

CREATE TABLE IF NOT EXISTS `ai_customer_conversation_message` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `message_id` char(36) NOT NULL COMMENT 'opaque message UUID',
  `conversation_id` char(36) NOT NULL,
  `sequence_no` int(11) NOT NULL,
  `role` varchar(16) NOT NULL COMMENT 'user or assistant only',
  `content` text NOT NULL COMMENT 'owner-visible transcript content',
  `public_response_json` text NULL COMMENT 'customer-safe response payload only',
  `create_time` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_customer_conversation_message_id` (`message_id`),
  UNIQUE KEY `uk_ai_customer_conversation_sequence` (`conversation_id`, `sequence_no`),
  KEY `idx_ai_customer_conversation_message_conversation` (`conversation_id`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Build19.1 customer-visible AI transcript';
