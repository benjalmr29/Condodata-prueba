from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from api.config import settings


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
)


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def tenant_session(condominio_id: int) -> Generator[Session, None, None]:
    """
    Abre una sesión con Row-Level Security activado para el tenant dado.
    Todas las queries dentro de este contexto solo ven datos de ese condominio.
    """
    with SessionLocal() as db:
        db.execute(
            text("SELECT set_config('app.condominio_id', :cid, true)"),
            {"cid": str(condominio_id)},
        )
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def check_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
