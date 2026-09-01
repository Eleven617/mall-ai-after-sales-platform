-- Build 18: one durable, transactionally-created after-sales event path.
--
-- The outbox belongs to the Java business transaction. RabbitMQ is deliberately
-- not a transaction participant: an unavailable broker leaves this row pending
-- for a later publisher retry instead of losing the committed business event.
CREATE TABLE IF NOT EXISTS `ai_after_sales_outbox` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `event_id` char(36) NOT NULL COMMENT 'stable event id used for consumer idempotency',
  `application_id` bigint(20) NOT NULL COMMENT 'oms_order_return_apply primary key',
  `member_id` bigint(20) NOT NULL COMMENT 'Java-authenticated owner, internal only',
  `event_type` varchar(64) NOT NULL COMMENT 'after_sales_application_created',
  `status` varchar(16) NOT NULL COMMENT 'PENDING, PUBLISHING, PUBLISHED, FAILED',
  `attempt_count` int(11) NOT NULL DEFAULT 0,
  `available_at` datetime NULL DEFAULT NULL COMMENT 'next eligible publish time',
  `lease_until` datetime NULL DEFAULT NULL COMMENT 'publisher crash-recovery lease',
  `published_at` datetime NULL DEFAULT NULL,
  `last_error` varchar(500) NULL DEFAULT NULL,
  `create_time` datetime NOT NULL,
  `update_time` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_after_sales_outbox_event_id` (`event_id`),
  KEY `idx_ai_after_sales_outbox_ready` (`status`, `available_at`),
  KEY `idx_ai_after_sales_outbox_application` (`application_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='AI after-sales transactional outbox';

-- The consumer writes this record before the RabbitMQ listener returns/acks.
-- A broker redelivery of the same event therefore becomes a no-op instead of a
-- second customer-visible notification/state transition.
CREATE TABLE IF NOT EXISTS `ai_after_sales_event_delivery` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `event_id` char(36) NOT NULL,
  `application_id` bigint(20) NOT NULL,
  `event_type` varchar(64) NOT NULL,
  `delivery_status` varchar(16) NOT NULL COMMENT 'DELIVERED',
  `delivered_at` datetime NOT NULL,
  `create_time` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_after_sales_delivery_event_id` (`event_id`),
  KEY `idx_ai_after_sales_delivery_application` (`application_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='AI after-sales event delivery idempotency';
