-- Build 19 phase B: a deliberately separate local developer identity for the
-- offline AI quality-evaluation page.  It has no operations, product or
-- super-admin role and no resource mapping; the narrow Java /ai/developer/me
-- controller verifies this role before FastAPI exposes synthetic eval results.
--
-- The migration is idempotent and only adds role/account/relation records. It
-- never changes customer members, orders, returns, CaseHandoffs or Outbox rows.

INSERT INTO ums_role (name, description, admin_count, create_time, status, sort)
SELECT 'AI质量开发者', '只能访问合成 AI 质量评测页面', 0, NOW(), 1, 0
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM ums_role WHERE name = 'AI质量开发者'
);

INSERT INTO ums_admin (
    username, password, icon, email, nick_name, note, create_time, login_time, status
)
SELECT
    'aiQualityDeveloper',
    '$2b$12$2bNOx6X4CUnd4Q7jHBLg9.kR79XZkr1HZ8fWbKOQYocJDNFB6kOcq',
    NULL, NULL, 'AI质量开发者', '本地合成评测专用账号', NOW(), NULL, 1
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM ums_admin WHERE username = 'aiQualityDeveloper'
);

INSERT INTO ums_admin_role_relation (admin_id, role_id)
SELECT admin.id, role.id
FROM ums_admin AS admin
JOIN ums_role AS role ON role.name = 'AI质量开发者'
WHERE admin.username = 'aiQualityDeveloper'
  AND NOT EXISTS (
      SELECT 1
      FROM ums_admin_role_relation AS relation_record
      WHERE relation_record.admin_id = admin.id
        AND relation_record.role_id = role.id
  );
