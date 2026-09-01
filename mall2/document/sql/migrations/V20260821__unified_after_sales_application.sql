-- Build 21: a new, generic after-sales application aggregate.
--
-- The legacy oms_order_return_apply table remains untouched for backward
-- compatibility. This table is the Java-owned core for new AI-created
-- cancellation/refund, return/refund, exchange and repair requests. It stores
-- only a request lifecycle; it never fabricates payment, carrier, warehouse or
-- repair-completion data.
CREATE TABLE IF NOT EXISTS `ai_after_sales_application` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `member_id` bigint(20) NOT NULL COMMENT 'Java-authenticated owner',
  `order_id` bigint(20) NOT NULL COMMENT 'owned oms_order id',
  `order_item_id` bigint(20) NULL DEFAULT NULL COMMENT 'owned oms_order_item id when item scoped',
  `order_sn` varchar(64) NOT NULL COMMENT 'customer-visible order number snapshot',
  `application_type` varchar(32) NOT NULL COMMENT 'cancel_refund, return_refund, exchange, repair',
  `product_name` varchar(200) NULL DEFAULT NULL COMMENT 'server-derived item snapshot',
  `product_attr` varchar(500) NULL DEFAULT NULL COMMENT 'server-derived item specification snapshot',
  `reason` varchar(100) NOT NULL COMMENT 'customer-provided reason',
  `description` varchar(500) NOT NULL DEFAULT '' COMMENT 'customer-provided detail',
  `status` varchar(32) NOT NULL COMMENT 'PENDING_REVIEW, ACCEPTED, COMPLETED, REJECTED, CANCELLED',
  `status_note` varchar(500) NULL DEFAULT NULL COMMENT 'customer-safe lifecycle note',
  `application_key` char(64) NOT NULL COMMENT 'internal immutable application key',
  `open_scope_key` varchar(180) NULL DEFAULT NULL COMMENT 'unique while an equivalent request is pending',
  `idempotency_key` char(32) NOT NULL COMMENT 'confirmation-bound submission key',
  `request_fingerprint` char(64) NOT NULL COMMENT 'SHA-256 canonical confirmed request',
  `create_time` datetime NOT NULL,
  `update_time` datetime NOT NULL,
  `cancelled_at` datetime NULL DEFAULT NULL,
  `reviewed_by` varchar(64) NULL DEFAULT NULL COMMENT 'authorized admin username, internal audit only',
  `reviewed_at` datetime NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_after_sales_application_key` (`application_key`),
  UNIQUE KEY `uk_ai_after_sales_member_idempotency` (`member_id`, `idempotency_key`),
  UNIQUE KEY `uk_ai_after_sales_open_scope` (`open_scope_key`),
  KEY `idx_ai_after_sales_member_created` (`member_id`, `create_time`),
  KEY `idx_ai_after_sales_order` (`order_id`),
  KEY `idx_ai_after_sales_review` (`status`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='AI unified after-sales applications';
