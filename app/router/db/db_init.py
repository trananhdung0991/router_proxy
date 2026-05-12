from .db import DB
from .clients import ClientsDB

class DBInit:
    def __init__(self):
        """Initialize all databases"""
        # Create the main DB connection first
        self.db = DB()
        # Pass the DB instance to ClientsDB
        self.clients_db = ClientsDB(self.db)
        