"""Shared declarative base for all ORM models in the project."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
