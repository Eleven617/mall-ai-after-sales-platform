-- Build 21 follow-up: migrate already-created local schemas without rewriting
-- existing applications.  The review audit supports a real human decision;
-- source labels prevent the shared Outbox from conflating legacy-return IDs
-- with IDs from the new unified aggregate.

SET @build21_schema = DATABASE();

SET @build21_has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = @build21_schema
      AND table_name = 'ai_after_sales_application'
      AND column_name = 'reviewed_by'
);
SET @build21_sql = IF(
    @build21_has_column = 0,
    'ALTER TABLE ai_after_sales_application ADD COLUMN reviewed_by varchar(64) NULL DEFAULT NULL COMMENT ''authorized admin username, internal audit only'' AFTER cancelled_at',
    'SELECT 1'
);
PREPARE build21_statement FROM @build21_sql;
EXECUTE build21_statement;
DEALLOCATE PREPARE build21_statement;

SET @build21_has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = @build21_schema
      AND table_name = 'ai_after_sales_application'
      AND column_name = 'reviewed_at'
);
SET @build21_sql = IF(
    @build21_has_column = 0,
    'ALTER TABLE ai_after_sales_application ADD COLUMN reviewed_at datetime NULL DEFAULT NULL AFTER reviewed_by',
    'SELECT 1'
);
PREPARE build21_statement FROM @build21_sql;
EXECUTE build21_statement;
DEALLOCATE PREPARE build21_statement;

SET @build21_has_index = (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = @build21_schema
      AND table_name = 'ai_after_sales_application'
      AND index_name = 'idx_ai_after_sales_review'
);
SET @build21_sql = IF(
    @build21_has_index = 0,
    'ALTER TABLE ai_after_sales_application ADD KEY idx_ai_after_sales_review (status, create_time)',
    'SELECT 1'
);
PREPARE build21_statement FROM @build21_sql;
EXECUTE build21_statement;
DEALLOCATE PREPARE build21_statement;

SET @build21_has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = @build21_schema
      AND table_name = 'ai_after_sales_outbox'
      AND column_name = 'application_source'
);
SET @build21_sql = IF(
    @build21_has_column = 0,
    'ALTER TABLE ai_after_sales_outbox ADD COLUMN application_source varchar(32) NOT NULL DEFAULT ''legacy_return'' COMMENT ''legacy_return or unified_after_sales'' AFTER member_id',
    'SELECT 1'
);
PREPARE build21_statement FROM @build21_sql;
EXECUTE build21_statement;
DEALLOCATE PREPARE build21_statement;

SET @build21_has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = @build21_schema
      AND table_name = 'ai_after_sales_event_delivery'
      AND column_name = 'application_source'
);
SET @build21_sql = IF(
    @build21_has_column = 0,
    'ALTER TABLE ai_after_sales_event_delivery ADD COLUMN application_source varchar(32) NOT NULL DEFAULT ''legacy_return'' COMMENT ''legacy_return or unified_after_sales'' AFTER application_id',
    'SELECT 1'
);
PREPARE build21_statement FROM @build21_sql;
EXECUTE build21_statement;
DEALLOCATE PREPARE build21_statement;
