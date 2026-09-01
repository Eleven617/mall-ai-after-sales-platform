-- Build 19.1 local rich-demo scenario library.
--
-- This file is deliberately NOT mounted as an automatic MySQL migration.
-- It is opt-in, idempotent, and inserts only records with the AI-DEMO-19-1
-- identifier. It does not delete, reset, or update ordinary local data.
-- The rows exist to make the operations aggregate view demonstrable.

INSERT INTO oms_order_return_apply (
  order_id, company_address_id, product_id, order_sn, create_time,
  member_username, return_amount, return_name, return_phone, status,
  handle_time, product_pic, product_name, product_brand, product_attr,
  product_count, product_price, product_real_price, reason, description,
  proof_pics, handle_note, handle_man, receive_man, receive_time, receive_note
)
SELECT NULL, NULL, NULL, 'AI-DEMO-19-1-RICH-001', NOW() - INTERVAL 1 DAY,
  'demo-scenario', 99.00, '演示账户', NULL, 0,
  NULL, NULL, '演示商品 A', '本地演示', '规格：演示',
  1, 99.00, 99.00, '质量问题', '本地演示：待人工审核',
  NULL, NULL, NULL, NULL, NULL, NULL
WHERE NOT EXISTS (
  SELECT 1 FROM oms_order_return_apply WHERE order_sn = 'AI-DEMO-19-1-RICH-001'
);

INSERT INTO oms_order_return_apply (
  order_id, company_address_id, product_id, order_sn, create_time,
  member_username, return_amount, return_name, return_phone, status,
  handle_time, product_pic, product_name, product_brand, product_attr,
  product_count, product_price, product_real_price, reason, description,
  proof_pics, handle_note, handle_man, receive_man, receive_time, receive_note
)
SELECT NULL, NULL, NULL, 'AI-DEMO-19-1-RICH-002', NOW() - INTERVAL 2 DAY,
  'demo-scenario', 129.00, '演示账户', NULL, 0,
  NULL, NULL, '演示商品 B', '本地演示', '规格：演示',
  1, 129.00, 129.00, '商品错发或漏发', '本地演示：待人工审核',
  NULL, NULL, NULL, NULL, NULL, NULL
WHERE NOT EXISTS (
  SELECT 1 FROM oms_order_return_apply WHERE order_sn = 'AI-DEMO-19-1-RICH-002'
);

INSERT INTO oms_order_return_apply (
  order_id, company_address_id, product_id, order_sn, create_time,
  member_username, return_amount, return_name, return_phone, status,
  handle_time, product_pic, product_name, product_brand, product_attr,
  product_count, product_price, product_real_price, reason, description,
  proof_pics, handle_note, handle_man, receive_man, receive_time, receive_note
)
SELECT NULL, NULL, NULL, 'AI-DEMO-19-1-RICH-003', NOW() - INTERVAL 3 DAY,
  'demo-scenario', 159.00, '演示账户', NULL, 0,
  NULL, NULL, '演示商品 C', '本地演示', '规格：演示',
  1, 159.00, 159.00, '商品与描述不符', '本地演示：待人工审核',
  NULL, NULL, NULL, NULL, NULL, NULL
WHERE NOT EXISTS (
  SELECT 1 FROM oms_order_return_apply WHERE order_sn = 'AI-DEMO-19-1-RICH-003'
);

INSERT INTO oms_order_return_apply (
  order_id, company_address_id, product_id, order_sn, create_time,
  member_username, return_amount, return_name, return_phone, status,
  handle_time, product_pic, product_name, product_brand, product_attr,
  product_count, product_price, product_real_price, reason, description,
  proof_pics, handle_note, handle_man, receive_man, receive_time, receive_note
)
SELECT NULL, NULL, NULL, 'AI-DEMO-19-1-RICH-004', NOW() - INTERVAL 4 DAY,
  'demo-scenario', 79.00, '演示账户', NULL, 1,
  NOW() - INTERVAL 2 DAY, NULL, '演示商品 D', '本地演示', '规格：演示',
  1, 79.00, 79.00, '七天无理由', '本地演示：已进入退货流程',
  NULL, '等待寄回', 'demo-operator', NULL, NULL, NULL
WHERE NOT EXISTS (
  SELECT 1 FROM oms_order_return_apply WHERE order_sn = 'AI-DEMO-19-1-RICH-004'
);

INSERT INTO oms_order_return_apply (
  order_id, company_address_id, product_id, order_sn, create_time,
  member_username, return_amount, return_name, return_phone, status,
  handle_time, product_pic, product_name, product_brand, product_attr,
  product_count, product_price, product_real_price, reason, description,
  proof_pics, handle_note, handle_man, receive_man, receive_time, receive_note
)
SELECT NULL, NULL, NULL, 'AI-DEMO-19-1-RICH-005', NOW() - INTERVAL 5 DAY,
  'demo-scenario', 189.00, '演示账户', NULL, 1,
  NOW() - INTERVAL 1 DAY, NULL, '演示商品 E', '本地演示', '规格：演示',
  1, 189.00, 189.00, '尺码不合适', '本地演示：已进入退货流程',
  NULL, '等待寄回', 'demo-operator', NULL, NULL, NULL
WHERE NOT EXISTS (
  SELECT 1 FROM oms_order_return_apply WHERE order_sn = 'AI-DEMO-19-1-RICH-005'
);

INSERT INTO oms_order_return_apply (
  order_id, company_address_id, product_id, order_sn, create_time,
  member_username, return_amount, return_name, return_phone, status,
  handle_time, product_pic, product_name, product_brand, product_attr,
  product_count, product_price, product_real_price, reason, description,
  proof_pics, handle_note, handle_man, receive_man, receive_time, receive_note
)
SELECT NULL, NULL, NULL, 'AI-DEMO-19-1-RICH-006', NOW() - INTERVAL 6 DAY,
  'demo-scenario', 219.00, '演示账户', NULL, 2,
  NOW() - INTERVAL 1 DAY, NULL, '演示商品 F', '本地演示', '规格：演示',
  1, 219.00, 219.00, '颜色/规格错误', '本地演示：售后已完成',
  NULL, '已完成', 'demo-operator', 'demo-warehouse', NOW() - INTERVAL 1 DAY, '演示签收'
WHERE NOT EXISTS (
  SELECT 1 FROM oms_order_return_apply WHERE order_sn = 'AI-DEMO-19-1-RICH-006'
);

INSERT INTO oms_order_return_apply (
  order_id, company_address_id, product_id, order_sn, create_time,
  member_username, return_amount, return_name, return_phone, status,
  handle_time, product_pic, product_name, product_brand, product_attr,
  product_count, product_price, product_real_price, reason, description,
  proof_pics, handle_note, handle_man, receive_man, receive_time, receive_note
)
SELECT NULL, NULL, NULL, 'AI-DEMO-19-1-RICH-007', NOW() - INTERVAL 2 DAY,
  'demo-scenario', 109.00, '演示账户', NULL, 3,
  NOW() - INTERVAL 1 DAY, NULL, '演示商品 G', '本地演示', '规格：演示',
  1, 109.00, 109.00, '商品瑕疵', '本地演示：申请被拒绝',
  NULL, '演示拒绝原因', 'demo-operator', NULL, NULL, NULL
WHERE NOT EXISTS (
  SELECT 1 FROM oms_order_return_apply WHERE order_sn = 'AI-DEMO-19-1-RICH-007'
);

INSERT INTO ai_after_sales_outbox (
  event_id, application_id, member_id, event_type, status, attempt_count,
  available_at, lease_until, published_at, last_error, create_time, update_time
)
SELECT '91000000-0000-4000-8000-000000000001', id, 1, 'after_sales_application_created',
  'PENDING', 0, NOW(), NULL, NULL, NULL, NOW() - INTERVAL 1 DAY, NOW()
FROM oms_order_return_apply
WHERE order_sn = 'AI-DEMO-19-1-RICH-001'
  AND NOT EXISTS (SELECT 1 FROM ai_after_sales_outbox WHERE event_id = '91000000-0000-4000-8000-000000000001');

INSERT INTO ai_after_sales_outbox (
  event_id, application_id, member_id, event_type, status, attempt_count,
  available_at, lease_until, published_at, last_error, create_time, update_time
)
SELECT '91000000-0000-4000-8000-000000000002', id, 1, 'after_sales_application_created',
  'PUBLISHING', 1, NOW(), NOW() + INTERVAL 5 MINUTE, NULL, NULL, NOW() - INTERVAL 2 DAY, NOW()
FROM oms_order_return_apply
WHERE order_sn = 'AI-DEMO-19-1-RICH-002'
  AND NOT EXISTS (SELECT 1 FROM ai_after_sales_outbox WHERE event_id = '91000000-0000-4000-8000-000000000002');

INSERT INTO ai_after_sales_outbox (
  event_id, application_id, member_id, event_type, status, attempt_count,
  available_at, lease_until, published_at, last_error, create_time, update_time
)
SELECT '91000000-0000-4000-8000-000000000003', id, 1, 'after_sales_application_created',
  'FAILED', 3, NOW() + INTERVAL 10 MINUTE, NULL, NULL, '本地演示失败分支', NOW() - INTERVAL 3 DAY, NOW()
FROM oms_order_return_apply
WHERE order_sn = 'AI-DEMO-19-1-RICH-003'
  AND NOT EXISTS (SELECT 1 FROM ai_after_sales_outbox WHERE event_id = '91000000-0000-4000-8000-000000000003');

INSERT INTO ai_after_sales_outbox (
  event_id, application_id, member_id, event_type, status, attempt_count,
  available_at, lease_until, published_at, last_error, create_time, update_time
)
SELECT '91000000-0000-4000-8000-000000000004', id, 1, 'after_sales_application_created',
  'PUBLISHED', 1, NOW(), NULL, NOW() - INTERVAL 1 DAY, NULL, NOW() - INTERVAL 4 DAY, NOW()
FROM oms_order_return_apply
WHERE order_sn = 'AI-DEMO-19-1-RICH-004'
  AND NOT EXISTS (SELECT 1 FROM ai_after_sales_outbox WHERE event_id = '91000000-0000-4000-8000-000000000004');

-- Keep the controlled queue branches stable on repeat runs. The normal local
-- publisher is allowed to process ordinary data; this one PENDING fixture is
-- intentionally delayed so the operations page can demonstrate a backlog.
UPDATE ai_after_sales_outbox
SET status = 'PENDING', attempt_count = 0, available_at = NOW() + INTERVAL 1 DAY,
    lease_until = NULL, published_at = NULL, last_error = NULL, update_time = NOW()
WHERE event_id = '91000000-0000-4000-8000-000000000001';

UPDATE ai_after_sales_outbox
SET status = 'PUBLISHING', attempt_count = 1, available_at = NOW(),
    lease_until = NOW() + INTERVAL 5 MINUTE, published_at = NULL, last_error = NULL,
    update_time = NOW()
WHERE event_id = '91000000-0000-4000-8000-000000000002';

UPDATE ai_after_sales_outbox
SET status = 'FAILED', attempt_count = 3, available_at = NOW() + INTERVAL 10 MINUTE,
    lease_until = NULL, published_at = NULL, last_error = '本地演示失败分支', update_time = NOW()
WHERE event_id = '91000000-0000-4000-8000-000000000003';

INSERT INTO ai_after_sales_event_delivery (
  event_id, application_id, event_type, delivery_status, delivered_at, create_time
)
SELECT '91000000-0000-4000-8000-000000000004', id, 'after_sales_application_created',
  'DELIVERED', NOW() - INTERVAL 1 DAY, NOW() - INTERVAL 1 DAY
FROM oms_order_return_apply
WHERE order_sn = 'AI-DEMO-19-1-RICH-004'
  AND NOT EXISTS (SELECT 1 FROM ai_after_sales_event_delivery WHERE event_id = '91000000-0000-4000-8000-000000000004');

INSERT INTO ai_case_handoff (
  case_id, member_id, case_key, source_flow, diagnosis_category, evidence_status,
  handoff_reason, requires_human_review, case_status, schema_version, create_time, update_time
) VALUES (
  '92000000-0000-4000-8000-000000000001', 1,
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa0001',
  'customer_diagnosis', 'policy_insufficient', 'insufficient',
  'insufficient_evidence', 1, 'OPEN', '1', NOW() - INTERVAL 1 DAY, NOW()
) ON DUPLICATE KEY UPDATE update_time = update_time;

INSERT INTO ai_case_handoff (
  case_id, member_id, case_key, source_flow, diagnosis_category, evidence_status,
  handoff_reason, requires_human_review, case_status, schema_version, create_time, update_time
) VALUES (
  '92000000-0000-4000-8000-000000000002', 1,
  'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb0002',
  'customer_diagnosis', 'tool_failure', 'unavailable',
  'tool_failure', 1, 'OPEN', '1', NOW() - INTERVAL 2 DAY, NOW()
) ON DUPLICATE KEY UPDATE update_time = update_time;
