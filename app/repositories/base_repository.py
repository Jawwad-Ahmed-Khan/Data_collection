"""
ClimaSync Collection Service — Base Repository
"""

from app.database.connection import DatabasePool

class BaseRepository:
    """Base class for all database repositories.
    
    Provides access to the shared database connection pool.
    """

    def __init__(self, db: DatabasePool) -> None:
        self.db = db
