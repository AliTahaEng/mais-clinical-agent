"""
User domain model.
Pure dataclass — no DB or framework coupling here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class User:
    id: str                          # UUID string
    email: str
    username: str
    hashed_password: str
    role: str                        # "user" | "admin"
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
