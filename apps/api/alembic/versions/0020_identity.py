"""최소 인증 스키마. 충돌은 자동 병합하지 않고 마이그레이션 전체를 거절한다."""

from pathlib import Path

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    sql = (Path(__file__).parents[1] / "sql/0020_identity.sql").read_text(
        encoding="utf-8"
    )
    for statement in sql.split("-- statement-break"):
        # Windows 기본 콘솔 인코딩에서도 오프라인 DDL을 전달할 수 있게 설명 주석만 제외한다.
        statement = "\n".join(
            line
            for line in statement.splitlines()
            if not line.lstrip().startswith("--")
        )
        if statement.strip():
            op.execute(statement)


def downgrade():
    # 인증 증명/세션을 조용히 삭제하면 서비스 보안 상태가 달라지므로 비어 있을 때만 허용한다.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM auth_sessions) OR EXISTS (SELECT 1 FROM auth_action_tokens)
           OR EXISTS (SELECT 1 FROM users WHERE email_verified OR pending_expires_at IS NOT NULL) THEN
            RAISE EXCEPTION 'Authentication data exists: restore a verified backup instead';
        END IF;
    END $$;""")
    for table in (
        "auth_rate_limits",
        "auth_oauth_attempts",
        "auth_action_tokens",
        "auth_sessions",
    ):
        op.drop_table(table)
    op.drop_column("users", "pending_expires_at")
    op.drop_column("users", "email_verified")
    op.drop_constraint("ck_users_email_normalized", "users", type_="check")
