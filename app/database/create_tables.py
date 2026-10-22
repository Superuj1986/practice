from sqlalchemy import text

from app.database.models import Base
from app.database.connection import engine


def ensure_database_schema() -> None:
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        connection.execute(
            text(
                "ALTER TABLE digests "
                "ADD COLUMN IF NOT EXISTS sent_at TIMESTAMP WITH TIME ZONE"
            )
        )


if __name__ == "__main__":
    ensure_database_schema()
    print("Tables created successfully")
