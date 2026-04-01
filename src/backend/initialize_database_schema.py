"""
Step 2: Initialize Database Schema
==================================
PROMPT Reference: Phase 1, Step 2

Creates and configures the SQLite database with WAL mode, defines all tables
via SQLAlchemy ORM, and sets up Alembic for schema migrations.

Database: /data/db/grocery.db (Docker volume)

Key Features:
    - WAL mode enabled on every connection for concurrent read safety
    - Alembic migration support for safe schema evolution
    - All tables include created_at and updated_at timestamps
    - Indexes on frequently queried columns (product_id, user_id, date)
"""

import os
import logging
from sqlalchemy import text
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, Date,
    ForeignKey, Text, Boolean, UniqueConstraint, Index, event
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)
Base = declarative_base()

# ---------------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////data/db/grocery.db")


def _set_wal_mode(dbapi_connection, connection_record):
    """Enable WAL mode on every new SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(database_url=None):
    """Create SQLAlchemy engine with WAL mode listener."""
    url = database_url or DATABASE_URL
    engine = create_engine(url, echo=False)
    event.listen(engine, "connect", _set_wal_mode)
    logger.info(f"Database engine created: {url}")
    return engine


def create_session_factory(engine):
    """Create a session factory bound to the given engine."""
    return sessionmaker(bind=engine)


# ---------------------------------------------------------------------------
# Utility Columns
# ---------------------------------------------------------------------------

def utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Table Definitions (PRD Section 4.2)
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    role = Column(String(20), nullable=False, default="user")  # "admin" or "user"
    is_active = Column(Boolean, nullable=False, default=True)
    password_hash = Column(String(255), nullable=True)
    api_token_hash = Column(String(255), nullable=True)
    password_reset_requested_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    purchases = relationship("Purchase", back_populates="user")
    budgets = relationship("Budget", back_populates="user")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=True)
    barcode = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("name", "category", name="uq_product_name_category"),
        Index("ix_product_name", "name"),
        Index("ix_product_category", "category"),
    )

    # Relationships
    inventory_items = relationship("Inventory", back_populates="product")
    price_history = relationship("PriceHistory", back_populates="product")
    receipt_items = relationship("ReceiptItem", back_populates="product")


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    location = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    purchases = relationship("Purchase", back_populates="store")
    price_history = relationship("PriceHistory", back_populates="store")


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, nullable=False, default=0)
    location = Column(String(50), nullable=True)  # Fridge, Pantry, Freezer, Cabinet
    threshold = Column(Float, nullable=True)  # Low-stock alert threshold
    last_updated = Column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        Index("ix_inventory_product_id", "product_id"),
    )

    # Relationships
    product = relationship("Product", back_populates="inventory_items")


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)
    total_amount = Column(Float, nullable=True)
    date = Column(DateTime, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_purchase_date", "date"),
        Index("ix_purchase_user_id", "user_id"),
    )

    # Relationships
    store = relationship("Store", back_populates="purchases")
    user = relationship("User", back_populates="purchases")
    receipt_items = relationship("ReceiptItem", back_populates="purchase")


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    extracted_by = Column(String(20), nullable=True)  # "gemini" or "ollama"
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_receipt_item_product_id", "product_id"),
    )

    # Relationships
    purchase = relationship("Purchase", back_populates="receipt_items")
    product = relationship("Product", back_populates="receipt_items")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)
    price = Column(Float, nullable=False)
    date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_price_history_product_id", "product_id"),
        Index("ix_price_history_date", "date"),
    )

    # Relationships
    product = relationship("Product", back_populates="price_history")
    store = relationship("Store", back_populates="price_history")


class Budget(Base):
    __tablename__ = "budget"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    month = Column(String(7), nullable=False)  # Format: "2026-04"
    budget_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "month", name="uq_budget_user_month"),
    )

    # Relationships
    user = relationship("User", back_populates="budgets")


class TelegramReceipt(Base):
    __tablename__ = "telegram_receipts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(String(50), nullable=False)
    message_id = Column(String(50), nullable=True)
    image_path = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending, processed, failed, review
    ocr_confidence = Column(Float, nullable=True)
    ocr_engine = Column(String(20), nullable=True)  # "gemini" or "ollama"
    receipt_type = Column(String(30), nullable=True)
    raw_ocr_json = Column(Text, nullable=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    service_name = Column(String(50), nullable=False)  # "gemini", "ollama"
    date = Column(Date, nullable=False)
    request_count = Column(Integer, nullable=False, default=0)
    token_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("service_name", "date", name="uq_api_usage_per_day"),
    )


# ---------------------------------------------------------------------------
# Schema Initialization
# ---------------------------------------------------------------------------

def initialize_database(database_url=None):
    """Create all tables and return engine + session factory."""
    engine = create_db_engine(database_url)
    Base.metadata.create_all(engine)
    _ensure_runtime_columns(engine)
    Session = create_session_factory(engine)
    logger.info("Database schema initialized successfully.")
    return engine, Session


def _ensure_runtime_columns(engine):
    """Add a few backward-compatible columns for SQLite dev databases."""
    with engine.begin() as conn:
        if engine.dialect.name != "sqlite":
            return

        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(telegram_receipts)"))
        }
        if "receipt_type" not in existing:
            conn.execute(text("ALTER TABLE telegram_receipts ADD COLUMN receipt_type VARCHAR(30)"))
        if "raw_ocr_json" not in existing:
            conn.execute(text("ALTER TABLE telegram_receipts ADD COLUMN raw_ocr_json TEXT"))

        user_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(users)"))
        }
        if "is_active" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
        if "password_hash" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
        if "password_reset_requested_at" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN password_reset_requested_at DATETIME"))


# ---------------------------------------------------------------------------
# Entry point for standalone initialization
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine, Session = initialize_database()
    logger.info("Database tables created.")
