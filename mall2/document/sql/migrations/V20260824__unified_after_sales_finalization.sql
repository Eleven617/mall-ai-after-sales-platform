-- Final unified after-sales cutover.
--
-- This migration is deliberately append-only until its last archive step.  It
-- first records a recoverable legacy copy and a row/owner/status reconciliation
-- audit, then removes the legacy table name only when every legacy submission
-- has a mapped unified application.  The original mall-wide
-- oms_order_return_apply table is not touched.

SET @uas_schema = DATABASE();

-- Application and fulfillment state are separate.  An accepted application is
-- never a claim that a payment refund, warehouse receipt or replacement has
-- completed.
SET @uas_has_fulfillment_status = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @uas_schema AND table_name = 'ai_after_sales_application'
    AND column_name = 'fulfillment_status'
);
SET @uas_sql = IF(
  @uas_has_fulfillment_status = 0,
  'ALTER TABLE ai_after_sales_application ADD COLUMN fulfillment_status varchar(32) NOT NULL DEFAULT ''NOT_STARTED'' AFTER status_note',
  'SELECT 1'
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

SET @uas_has_fulfillment_note = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @uas_schema AND table_name = 'ai_after_sales_application'
    AND column_name = 'fulfillment_note'
);
SET @uas_sql = IF(
  @uas_has_fulfillment_note = 0,
  'ALTER TABLE ai_after_sales_application ADD COLUMN fulfillment_note varchar(500) NULL DEFAULT NULL AFTER fulfillment_status',
  'SELECT 1'
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

SET @uas_has_fulfillment_updated_at = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @uas_schema AND table_name = 'ai_after_sales_application'
    AND column_name = 'fulfillment_updated_at'
);
SET @uas_sql = IF(
  @uas_has_fulfillment_updated_at = 0,
  'ALTER TABLE ai_after_sales_application ADD COLUMN fulfillment_updated_at datetime NULL DEFAULT NULL AFTER fulfillment_note',
  'SELECT 1'
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

SET @uas_has_customer_supplement = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @uas_schema AND table_name = 'ai_after_sales_application'
    AND column_name = 'customer_supplement'
);
SET @uas_sql = IF(
  @uas_has_customer_supplement = 0,
  'ALTER TABLE ai_after_sales_application ADD COLUMN customer_supplement varchar(500) NULL DEFAULT NULL AFTER description',
  'SELECT 1'
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

CREATE TABLE IF NOT EXISTS ai_after_sales_action (
  id bigint(20) NOT NULL AUTO_INCREMENT,
  member_id bigint(20) NOT NULL,
  application_id bigint(20) NOT NULL,
  action_id char(32) NOT NULL,
  action_type varchar(16) NOT NULL COMMENT 'cancel or modify',
  content_hash char(64) NOT NULL,
  result_status varchar(16) NOT NULL COMMENT 'COMPLETED',
  create_time datetime NOT NULL,
  update_time datetime NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_ai_after_sales_action_member_action (member_id, action_id),
  KEY idx_ai_after_sales_action_application (application_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='confirmed unified after-sales write idempotency';

CREATE TABLE IF NOT EXISTS ai_after_sales_fulfillment_callback (
  id bigint(20) NOT NULL AUTO_INCREMENT,
  callback_event_id varchar(64) NOT NULL,
  application_id bigint(20) NOT NULL,
  fulfillment_status varchar(32) NOT NULL,
  source varchar(32) NOT NULL,
  note varchar(500) NULL DEFAULT NULL,
  callback_time datetime NOT NULL,
  create_time datetime NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_ai_after_sales_fulfillment_callback_event (callback_event_id),
  KEY idx_ai_after_sales_fulfillment_callback_application (application_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='idempotent fulfillment callback audit';

CREATE TABLE IF NOT EXISTS ai_after_sales_legacy_mapping (
  legacy_submission_id bigint(20) NOT NULL,
  unified_application_id bigint(20) NOT NULL,
  legacy_member_id bigint(20) NOT NULL,
  legacy_return_apply_id bigint(20) NULL DEFAULT NULL,
  mapped_at datetime NOT NULL,
  PRIMARY KEY (legacy_submission_id),
  UNIQUE KEY uk_ai_after_sales_legacy_mapping_unified (unified_application_id),
  KEY idx_ai_after_sales_legacy_mapping_member (legacy_member_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='auditable Build16 legacy to unified mapping';

CREATE TABLE IF NOT EXISTS ai_after_sales_migration_audit (
  migration_version varchar(64) NOT NULL,
  source_table varchar(96) NULL DEFAULT NULL,
  source_count bigint(20) NOT NULL DEFAULT 0,
  mapped_count bigint(20) NOT NULL DEFAULT 0,
  owner_mismatch_count bigint(20) NOT NULL DEFAULT 0,
  status_unmapped_count bigint(20) NOT NULL DEFAULT 0,
  verified tinyint(1) NOT NULL DEFAULT 0,
  recorded_at datetime NOT NULL,
  PRIMARY KEY (migration_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='final unified after-sales migration reconciliation';

-- The old outbox used the legacy oms_order_return_apply primary key.  These
-- rows are part of the same cutover: leaving their source discriminator in
-- place would retain a hidden second runtime data path even after the public
-- return flow and submission table are gone.
CREATE TABLE IF NOT EXISTS ai_after_sales_event_migration_audit (
  migration_version varchar(64) NOT NULL,
  legacy_outbox_count bigint(20) NOT NULL DEFAULT 0,
  mapped_outbox_count bigint(20) NOT NULL DEFAULT 0,
  unmapped_outbox_count bigint(20) NOT NULL DEFAULT 0,
  legacy_delivery_count bigint(20) NOT NULL DEFAULT 0,
  mapped_delivery_count bigint(20) NOT NULL DEFAULT 0,
  unmapped_delivery_count bigint(20) NOT NULL DEFAULT 0,
  verified tinyint(1) NOT NULL DEFAULT 0,
  recorded_at datetime NOT NULL,
  PRIMARY KEY (migration_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='legacy after-sales event to unified aggregate reconciliation';

-- Events that cannot be bound to a valid legacy submission are never guessed
-- into a new application.  In the supplied demo data, these are old return
-- fixtures with no order_id at all.  They are preserved in explicit archive
-- tables outside the runtime Outbox rather than being silently discarded or
-- turned into a customer-visible unified application.
CREATE TABLE IF NOT EXISTS ai_after_sales_outbox_legacy_archive_20260824 LIKE ai_after_sales_outbox;
CREATE TABLE IF NOT EXISTS ai_after_sales_event_delivery_legacy_archive_20260824 LIKE ai_after_sales_event_delivery;

SET @uas_has_outbox_archive_reason = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @uas_schema
    AND table_name = 'ai_after_sales_outbox_legacy_archive_20260824'
    AND column_name = 'archive_reason'
);
SET @uas_sql = IF(
  @uas_has_outbox_archive_reason = 0,
  'ALTER TABLE ai_after_sales_outbox_legacy_archive_20260824 ADD COLUMN archive_reason varchar(96) NOT NULL AFTER update_time, ADD COLUMN archived_at datetime NOT NULL AFTER archive_reason',
  'SELECT 1'
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

SET @uas_has_delivery_archive_reason = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @uas_schema
    AND table_name = 'ai_after_sales_event_delivery_legacy_archive_20260824'
    AND column_name = 'archive_reason'
);
SET @uas_sql = IF(
  @uas_has_delivery_archive_reason = 0,
  'ALTER TABLE ai_after_sales_event_delivery_legacy_archive_20260824 ADD COLUMN archive_reason varchar(96) NOT NULL AFTER create_time, ADD COLUMN archived_at datetime NOT NULL AFTER archive_reason',
  'SELECT 1'
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

CREATE TABLE IF NOT EXISTS ai_after_sales_legacy_event_archive_audit (
  migration_version varchar(64) NOT NULL,
  source_table varchar(96) NOT NULL,
  archived_count bigint(20) NOT NULL DEFAULT 0,
  archive_reason varchar(96) NOT NULL,
  verified tinyint(1) NOT NULL DEFAULT 0,
  recorded_at datetime NOT NULL,
  PRIMARY KEY (migration_version, source_table)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='audited archive of unmigratable legacy after-sales fixtures';

-- Resolve either the live old name (first run) or the recoverable archive
-- (subsequent runs); this makes mysql-migrate safe to execute repeatedly.
SET @uas_live_legacy_exists = (
  SELECT COUNT(*) FROM information_schema.tables
  WHERE table_schema = @uas_schema AND table_name = 'ai_return_submission'
);
SET @uas_archive_legacy_exists = (
  SELECT COUNT(*) FROM information_schema.tables
  WHERE table_schema = @uas_schema AND table_name = 'ai_return_submission_legacy_archive_20260824'
);
SET @uas_legacy_source = IF(
  @uas_live_legacy_exists > 0,
  'ai_return_submission',
  IF(@uas_archive_legacy_exists > 0, 'ai_return_submission_legacy_archive_20260824', NULL)
);

-- Only legacy records that actually created an oms_order_return_apply are
-- migratable.  The old table did not persist a unified lifecycle; the mapping
-- preserves its real existing status rather than inventing a new fulfillment.
SET @uas_sql = IF(
  @uas_legacy_source IS NULL,
  'SELECT 1',
  CONCAT(
    'INSERT IGNORE INTO ai_after_sales_application (',
    'member_id, order_id, order_item_id, order_sn, application_type, ',
    'product_name, product_attr, reason, description, customer_supplement, ',
    'status, status_note, fulfillment_status, fulfillment_note, fulfillment_updated_at, ',
    'application_key, open_scope_key, idempotency_key, request_fingerprint, ',
    'create_time, update_time, cancelled_at, reviewed_by, reviewed_at) ',
    'SELECT s.member_id, r.order_id, oi.id, r.order_sn, ''return_refund'', ',
    'r.product_name, r.product_attr, COALESCE(NULLIF(r.reason, ''''), ''历史退货申请''), ',
    'COALESCE(r.description, ''''), NULL, ',
    'CASE r.status WHEN 0 THEN ''PENDING_REVIEW'' WHEN 1 THEN ''ACCEPTED'' ',
    'WHEN 2 THEN ''COMPLETED'' WHEN 3 THEN ''REJECTED'' ELSE ''PENDING_REVIEW'' END, ',
    'NULLIF(r.handle_note, ''''), ',
    'CASE r.status WHEN 1 THEN ''PROCESSING'' WHEN 2 THEN ''SUCCEEDED'' ',
    'ELSE ''NOT_STARTED'' END, ',
    'CASE WHEN r.status = 2 THEN ''历史记录显示原退货流程已完成'' ',
    'WHEN r.status = 1 THEN ''历史记录显示原退货流程处理中'' ELSE NULL END, ',
    'CASE WHEN r.status IN (1,2) THEN COALESCE(r.handle_time, r.create_time) ELSE NULL END, ',
    'SHA2(CONCAT(''legacy-return-submission:'', s.id), 256), NULL, ',
    'SUBSTRING(SHA2(CONCAT(''legacy-return-idempotency:'', s.id), 256), 1, 32), ',
    'COALESCE(NULLIF(s.request_fingerprint, ''''), SHA2(CONCAT(''legacy-return-fingerprint:'', s.id), 256)), ',
    'COALESCE(s.create_time, r.create_time, NOW()), COALESCE(s.update_time, r.create_time, NOW()), ',
    'NULL, NULL, NULL ',
    'FROM ', @uas_legacy_source, ' s ',
    'INNER JOIN oms_order_return_apply r ON r.id = s.return_apply_id ',
    'LEFT JOIN oms_order_item oi ON oi.order_id = r.order_id AND oi.product_id = r.product_id ',
    'WHERE s.return_apply_id IS NOT NULL'
  )
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

-- Build the audit mapping from stable legacy-derived application keys.
SET @uas_sql = IF(
  @uas_legacy_source IS NULL,
  'SELECT 1',
  CONCAT(
    'INSERT IGNORE INTO ai_after_sales_legacy_mapping ',
    '(legacy_submission_id, unified_application_id, legacy_member_id, legacy_return_apply_id, mapped_at) ',
    'SELECT s.id, a.id, s.member_id, s.return_apply_id, NOW() ',
    'FROM ', @uas_legacy_source, ' s ',
    'INNER JOIN ai_after_sales_application a ',
    'ON a.application_key = SHA2(CONCAT(''legacy-return-submission:'', s.id), 256) ',
    'WHERE s.return_apply_id IS NOT NULL'
  )
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

SET @uas_sql = IF(
  @uas_legacy_source IS NULL,
  'INSERT INTO ai_after_sales_migration_audit (migration_version, source_table, source_count, mapped_count, owner_mismatch_count, status_unmapped_count, verified, recorded_at) VALUES (''V20260824'', NULL, 0, 0, 0, 0, 1, NOW()) ON DUPLICATE KEY UPDATE recorded_at = NOW()',
  CONCAT(
    'INSERT INTO ai_after_sales_migration_audit ',
    '(migration_version, source_table, source_count, mapped_count, owner_mismatch_count, status_unmapped_count, verified, recorded_at) ',
    'SELECT ''V20260824'', ''', @uas_legacy_source, ''', ',
    '(SELECT COUNT(*) FROM ', @uas_legacy_source, ' WHERE return_apply_id IS NOT NULL), ',
    '(SELECT COUNT(*) FROM ai_after_sales_legacy_mapping), ',
    '(SELECT COUNT(*) FROM ai_after_sales_legacy_mapping m ',
    'INNER JOIN ', @uas_legacy_source, ' s ON s.id = m.legacy_submission_id ',
    'INNER JOIN ai_after_sales_application a ON a.id = m.unified_application_id ',
    'WHERE s.member_id <> a.member_id), ',
    '(SELECT COUNT(*) FROM ', @uas_legacy_source, ' s ',
    'LEFT JOIN ai_after_sales_legacy_mapping m ON m.legacy_submission_id = s.id ',
    'WHERE s.return_apply_id IS NOT NULL AND m.legacy_submission_id IS NULL), ',
    'CASE WHEN ',
    '(SELECT COUNT(*) FROM ', @uas_legacy_source, ' WHERE return_apply_id IS NOT NULL) = ',
    '(SELECT COUNT(*) FROM ai_after_sales_legacy_mapping) ',
    'AND (SELECT COUNT(*) FROM ai_after_sales_legacy_mapping m ',
    'INNER JOIN ', @uas_legacy_source, ' s ON s.id = m.legacy_submission_id ',
    'INNER JOIN ai_after_sales_application a ON a.id = m.unified_application_id ',
    'WHERE s.member_id <> a.member_id) = 0 THEN 1 ELSE 0 END, NOW() ',
    'ON DUPLICATE KEY UPDATE source_table=VALUES(source_table), source_count=VALUES(source_count), ',
    'mapped_count=VALUES(mapped_count), owner_mismatch_count=VALUES(owner_mismatch_count), ',
    'status_unmapped_count=VALUES(status_unmapped_count), verified=VALUES(verified), recorded_at=NOW()'
  )
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

-- Reconcile committed legacy Outbox/delivery rows before the old submission
-- table is archived.  A normal match must be unique: ambiguity is a failed
-- migration, never a guess at which new application should receive an event.
SET @uas_legacy_outbox_count = (
  SELECT COUNT(*) FROM ai_after_sales_outbox
  WHERE application_source = 'legacy_return'
);
SET @uas_legacy_outbox_mapped_count = (
  SELECT COUNT(*)
  FROM ai_after_sales_outbox o
  INNER JOIN (
    SELECT legacy_return_apply_id, legacy_member_id,
           MIN(unified_application_id) AS unified_application_id
    FROM ai_after_sales_legacy_mapping
    WHERE legacy_return_apply_id IS NOT NULL
    GROUP BY legacy_return_apply_id, legacy_member_id
    HAVING COUNT(*) = 1
  ) m ON m.legacy_return_apply_id = o.application_id
      AND m.legacy_member_id = o.member_id
  WHERE o.application_source = 'legacy_return'
);
SET @uas_legacy_outbox_archive_count = (
  SELECT COUNT(*)
  FROM ai_after_sales_outbox o
  LEFT JOIN (
    SELECT legacy_return_apply_id, legacy_member_id,
           MIN(unified_application_id) AS unified_application_id
    FROM ai_after_sales_legacy_mapping
    WHERE legacy_return_apply_id IS NOT NULL
    GROUP BY legacy_return_apply_id, legacy_member_id
    HAVING COUNT(*) = 1
  ) m ON m.legacy_return_apply_id = o.application_id
      AND m.legacy_member_id = o.member_id
  INNER JOIN oms_order_return_apply r ON r.id = o.application_id
  WHERE o.application_source = 'legacy_return'
    AND m.unified_application_id IS NULL
    AND r.order_id IS NULL
);
SET @uas_legacy_outbox_unmapped_count =
  @uas_legacy_outbox_count - @uas_legacy_outbox_mapped_count - @uas_legacy_outbox_archive_count;

SET @uas_legacy_delivery_count = (
  SELECT COUNT(*) FROM ai_after_sales_event_delivery
  WHERE application_source = 'legacy_return'
);
SET @uas_legacy_delivery_mapped_count = (
  SELECT COUNT(*)
  FROM ai_after_sales_event_delivery d
  INNER JOIN (
    SELECT legacy_return_apply_id, MIN(unified_application_id) AS unified_application_id
    FROM ai_after_sales_legacy_mapping
    WHERE legacy_return_apply_id IS NOT NULL
    GROUP BY legacy_return_apply_id
    HAVING COUNT(*) = 1
  ) m ON m.legacy_return_apply_id = d.application_id
  WHERE d.application_source = 'legacy_return'
);
SET @uas_legacy_delivery_archive_count = (
  SELECT COUNT(*)
  FROM ai_after_sales_event_delivery d
  LEFT JOIN (
    SELECT legacy_return_apply_id, MIN(unified_application_id) AS unified_application_id
    FROM ai_after_sales_legacy_mapping
    WHERE legacy_return_apply_id IS NOT NULL
    GROUP BY legacy_return_apply_id
    HAVING COUNT(*) = 1
  ) m ON m.legacy_return_apply_id = d.application_id
  INNER JOIN oms_order_return_apply r ON r.id = d.application_id
  WHERE d.application_source = 'legacy_return'
    AND m.unified_application_id IS NULL
    AND r.order_id IS NULL
);
SET @uas_legacy_delivery_unmapped_count =
  @uas_legacy_delivery_count - @uas_legacy_delivery_mapped_count - @uas_legacy_delivery_archive_count;

-- A record without an order cannot meet the unified aggregate's factual
-- contract. Preserve it verbatim as audited historical data, then remove it
-- from the active event tables so no legacy runtime path remains.
INSERT IGNORE INTO ai_after_sales_outbox_legacy_archive_20260824 (
  id, event_id, application_id, member_id, application_source, event_type,
  status, attempt_count, available_at, lease_until, published_at, last_error,
  create_time, update_time, archive_reason, archived_at
)
SELECT o.id, o.event_id, o.application_id, o.member_id, o.application_source,
       o.event_type, o.status, o.attempt_count, o.available_at, o.lease_until,
       o.published_at, o.last_error, o.create_time, o.update_time,
       'LEGACY_RETURN_MISSING_ORDER', NOW()
FROM ai_after_sales_outbox o
LEFT JOIN (
  SELECT legacy_return_apply_id, legacy_member_id,
         MIN(unified_application_id) AS unified_application_id
  FROM ai_after_sales_legacy_mapping
  WHERE legacy_return_apply_id IS NOT NULL
  GROUP BY legacy_return_apply_id, legacy_member_id
  HAVING COUNT(*) = 1
) m ON m.legacy_return_apply_id = o.application_id
    AND m.legacy_member_id = o.member_id
INNER JOIN oms_order_return_apply r ON r.id = o.application_id
WHERE o.application_source = 'legacy_return'
  AND m.unified_application_id IS NULL
  AND r.order_id IS NULL;

DELETE o
FROM ai_after_sales_outbox o
INNER JOIN ai_after_sales_outbox_legacy_archive_20260824 a ON a.id = o.id
WHERE o.application_source = 'legacy_return'
  AND a.archive_reason = 'LEGACY_RETURN_MISSING_ORDER';

INSERT IGNORE INTO ai_after_sales_event_delivery_legacy_archive_20260824 (
  id, event_id, application_id, application_source, event_type, delivery_status,
  delivered_at, create_time, archive_reason, archived_at
)
SELECT d.id, d.event_id, d.application_id, d.application_source, d.event_type,
       d.delivery_status, d.delivered_at, d.create_time,
       'LEGACY_RETURN_MISSING_ORDER', NOW()
FROM ai_after_sales_event_delivery d
LEFT JOIN (
  SELECT legacy_return_apply_id, MIN(unified_application_id) AS unified_application_id
  FROM ai_after_sales_legacy_mapping
  WHERE legacy_return_apply_id IS NOT NULL
  GROUP BY legacy_return_apply_id
  HAVING COUNT(*) = 1
) m ON m.legacy_return_apply_id = d.application_id
INNER JOIN oms_order_return_apply r ON r.id = d.application_id
WHERE d.application_source = 'legacy_return'
  AND m.unified_application_id IS NULL
  AND r.order_id IS NULL;

DELETE d
FROM ai_after_sales_event_delivery d
INNER JOIN ai_after_sales_event_delivery_legacy_archive_20260824 a ON a.id = d.id
WHERE d.application_source = 'legacy_return'
  AND a.archive_reason = 'LEGACY_RETURN_MISSING_ORDER';

SET @uas_event_mapping_verified = IF(
  @uas_legacy_outbox_unmapped_count = 0
  AND @uas_legacy_delivery_unmapped_count = 0,
  1,
  0
);

-- Keep both the active mapping results and the exceptional archival result.
-- Later idempotent executions see zero legacy-source rows and must not erase
-- the first successful reconciliation evidence.
INSERT INTO ai_after_sales_event_migration_audit (
  migration_version, legacy_outbox_count, mapped_outbox_count, unmapped_outbox_count,
  legacy_delivery_count, mapped_delivery_count, unmapped_delivery_count, verified, recorded_at
) VALUES (
  'V20260824', @uas_legacy_outbox_count,
  @uas_legacy_outbox_mapped_count,
  @uas_legacy_outbox_unmapped_count,
  @uas_legacy_delivery_count,
  @uas_legacy_delivery_mapped_count,
  @uas_legacy_delivery_unmapped_count,
  @uas_event_mapping_verified, NOW()
) ON DUPLICATE KEY UPDATE
  legacy_outbox_count = IF(verified = 1, legacy_outbox_count, VALUES(legacy_outbox_count)),
  mapped_outbox_count = IF(verified = 1, mapped_outbox_count, VALUES(mapped_outbox_count)),
  unmapped_outbox_count = IF(verified = 1, unmapped_outbox_count, VALUES(unmapped_outbox_count)),
  legacy_delivery_count = IF(verified = 1, legacy_delivery_count, VALUES(legacy_delivery_count)),
  mapped_delivery_count = IF(verified = 1, mapped_delivery_count, VALUES(mapped_delivery_count)),
  unmapped_delivery_count = IF(verified = 1, unmapped_delivery_count, VALUES(unmapped_delivery_count)),
  verified = IF(verified = 1, 1, VALUES(verified)),
  recorded_at = NOW();

INSERT INTO ai_after_sales_legacy_event_archive_audit (
  migration_version, source_table, archived_count, archive_reason, verified, recorded_at
) VALUES
  ('V20260824', 'ai_after_sales_outbox', @uas_legacy_outbox_archive_count, 'LEGACY_RETURN_MISSING_ORDER', @uas_event_mapping_verified, NOW()),
  ('V20260824', 'ai_after_sales_event_delivery', @uas_legacy_delivery_archive_count, 'LEGACY_RETURN_MISSING_ORDER', @uas_event_mapping_verified, NOW())
ON DUPLICATE KEY UPDATE
  archived_count = IF(verified = 1, archived_count, VALUES(archived_count)),
  archive_reason = IF(verified = 1, archive_reason, VALUES(archive_reason)),
  verified = IF(verified = 1, 1, VALUES(verified)),
  recorded_at = NOW();

UPDATE ai_after_sales_outbox o
INNER JOIN (
  SELECT legacy_return_apply_id, legacy_member_id,
         MIN(unified_application_id) AS unified_application_id
  FROM ai_after_sales_legacy_mapping
  WHERE legacy_return_apply_id IS NOT NULL
  GROUP BY legacy_return_apply_id, legacy_member_id
  HAVING COUNT(*) = 1
) m ON m.legacy_return_apply_id = o.application_id
    AND m.legacy_member_id = o.member_id
SET o.application_id = m.unified_application_id,
    o.application_source = 'unified_after_sales',
    o.update_time = NOW()
WHERE o.application_source = 'legacy_return'
  AND @uas_event_mapping_verified = 1;

UPDATE ai_after_sales_event_delivery d
INNER JOIN (
  SELECT legacy_return_apply_id, MIN(unified_application_id) AS unified_application_id
  FROM ai_after_sales_legacy_mapping
  WHERE legacy_return_apply_id IS NOT NULL
  GROUP BY legacy_return_apply_id
  HAVING COUNT(*) = 1
) m ON m.legacy_return_apply_id = d.application_id
SET d.application_id = m.unified_application_id,
    d.application_source = 'unified_after_sales'
WHERE d.application_source = 'legacy_return'
  AND @uas_event_mapping_verified = 1;

-- A legacy submission mapping alone is not enough; only a fully reconciled
-- event history permits the old table name to disappear.
UPDATE ai_after_sales_migration_audit
SET verified = CASE
      WHEN verified = 1 AND @uas_event_mapping_verified = 1 THEN 1
      ELSE 0
    END,
    recorded_at = NOW()
WHERE migration_version = 'V20260824';

-- Replace the old *table name* with an explicit archive only after the audited
-- mapping passes.  The archive is data-only (no runtime fallback); Git tag and
-- this archive make the cutover recoverable without retaining two APIs.
SET @uas_verified = (
  SELECT verified FROM ai_after_sales_migration_audit WHERE migration_version = 'V20260824'
);

-- Compose must not start the new Java runtime against an unreconciled legacy
-- dataset. MySQL 5.7 cannot execute SIGNAL through a prepared statement, so
-- the false branch deliberately selects a non-existent table instead. That is
-- still a hard, deterministic failure without pretending a bad cutover passed.
SET @uas_sql = IF(
  @uas_verified = 1,
  'SELECT ''unified after-sales migration verified'' AS cutover_check',
  'SELECT * FROM __unified_after_sales_cutover_blocked__'
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

SET @uas_sql = IF(
  @uas_live_legacy_exists > 0 AND @uas_archive_legacy_exists = 0 AND @uas_verified = 1,
  'RENAME TABLE ai_return_submission TO ai_return_submission_legacy_archive_20260824',
  'SELECT 1'
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

-- Once every historical event references the unified aggregate, new writes
-- and new deployments have no legacy default or runtime fallback left.
SET @uas_sql = IF(
  @uas_verified = 1,
  'ALTER TABLE ai_after_sales_outbox MODIFY COLUMN application_source varchar(32) NOT NULL DEFAULT ''unified_after_sales'' COMMENT ''unified after-sales aggregate only''',
  'SELECT 1'
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

SET @uas_sql = IF(
  @uas_verified = 1,
  'ALTER TABLE ai_after_sales_outbox MODIFY COLUMN application_id bigint(20) NOT NULL COMMENT ''unified AI after-sales application primary key''',
  'SELECT 1'
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

SET @uas_sql = IF(
  @uas_verified = 1,
  'ALTER TABLE ai_after_sales_event_delivery MODIFY COLUMN application_id bigint(20) NOT NULL COMMENT ''unified AI after-sales application primary key''',
  'SELECT 1'
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;

SET @uas_sql = IF(
  @uas_verified = 1,
  'ALTER TABLE ai_after_sales_event_delivery MODIFY COLUMN application_source varchar(32) NOT NULL DEFAULT ''unified_after_sales'' COMMENT ''unified after-sales aggregate only''',
  'SELECT 1'
);
PREPARE uas_statement FROM @uas_sql; EXECUTE uas_statement; DEALLOCATE PREPARE uas_statement;
