from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def make_session_factory(url: str) -> sessionmaker:
    engine = create_engine(url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
