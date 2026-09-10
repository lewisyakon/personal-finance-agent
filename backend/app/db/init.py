from app.db.session import engine
from app.models import finance  # noqa: F401  # register model metadata
from app.models.base import Base


def init_database() -> None:
    """Create local MVP tables when migrations have not been run yet.

    Alembic remains the upgrade path for packaged deployments; create_all keeps
    the single-process local app usable immediately after checkout.
    """

    Base.metadata.create_all(bind=engine)
