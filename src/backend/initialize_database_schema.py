"""
Step 2: Initialize Database Schema
==================================
PROMPT Reference: Phase 1, Step 2

Creates and configures the SQLite database with WAL mode, defines all tables
via SQLAlchemy ORM, and sets up Alembic for schema migrations.

Database: /data/db/localocr_extended.db (Docker volume)

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

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////data/db/localocr_extended.db")


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
    avatar_emoji = Column(String(16), nullable=True)
    password_hash = Column(String(255), nullable=True)
    api_token_hash = Column(String(255), nullable=True)
    password_reset_requested_at = Column(DateTime, nullable=True)
    session_version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    purchases = relationship("Purchase", back_populates="user")
    budgets = relationship("Budget", back_populates="user")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    raw_name = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=True)
    brand = Column(String(120), nullable=True)
    size = Column(String(80), nullable=True)
    default_unit = Column(String(40), nullable=True)
    default_size_label = Column(String(120), nullable=True)
    enrichment_confidence = Column(Float, nullable=True)
    enriched_at = Column(DateTime, nullable=True)
    review_state = Column(String(20), nullable=True, default="pending")  # pending, resolved, dismissed
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
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
    manual_low = Column(Boolean, nullable=False, default=False)
    is_active_window = Column(Boolean, nullable=False, default=True)
    last_updated = Column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        Index("ix_inventory_product_id", "product_id"),
    )

    # Relationships
    product = relationship("Product", back_populates="inventory_items")


class InventoryAdjustment(Base):
    __tablename__ = "inventory_adjustments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity_delta = Column(Float, nullable=False, default=0)
    reason = Column(String(50), nullable=True)  # receipt_window, manual_add, consume, update, delete
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_inventory_adjustment_product_id", "product_id"),
        Index("ix_inventory_adjustment_created_at", "created_at"),
    )


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)
    total_amount = Column(Float, nullable=True)
    date = Column(DateTime, nullable=False)
    domain = Column(String(30), nullable=False, default="grocery")
    transaction_type = Column(String(20), nullable=False, default="purchase")
    refund_reason = Column(String(40), nullable=True)
    refund_note = Column(String(500), nullable=True)
    default_spending_domain = Column(String(30), nullable=False, default="grocery")
    default_budget_category = Column(String(40), nullable=False, default="grocery")
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
    unit = Column(String(40), nullable=True)
    size_label = Column(String(120), nullable=True)
    spending_domain = Column(String(30), nullable=True)
    budget_category = Column(String(40), nullable=True)
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
    domain = Column(String(30), nullable=False, default="grocery")
    budget_category = Column(String(40), nullable=True)
    budget_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "month", "domain", name="uq_budget_user_month_domain"),
    )

    # Relationships
    user = relationship("User", back_populates="budgets")


class BudgetChangeLog(Base):
    __tablename__ = "budget_change_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    month = Column(String(7), nullable=False)
    domain = Column(String(30), nullable=False, default="grocery")
    budget_category = Column(String(40), nullable=True)
    previous_amount = Column(Float, nullable=True)
    new_amount = Column(Float, nullable=False)
    changed_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_budget_change_log_user_month", "user_id", "month"),
        Index("ix_budget_change_log_category", "budget_category"),
    )


class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=True)
    quantity = Column(Float, nullable=False, default=1)
    unit = Column(String(40), nullable=True)
    size_label = Column(String(120), nullable=True)
    status = Column(String(20), nullable=False, default="open")  # open, purchased
    source = Column(String(30), nullable=True)  # recommendation, inventory, product, manual
    note = Column(String(500), nullable=True)
    preferred_store = Column(String(120), nullable=True)
    manual_estimated_price = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_shopping_list_status", "status"),
        Index("ix_shopping_list_user_id", "user_id"),
        Index("ix_shopping_list_product_id", "product_id"),
    )


class ProductSnapshot(Base):
    __tablename__ = "product_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    shopping_list_item_id = Column(Integer, ForeignKey("shopping_list_items.id"), nullable=True)
    receipt_item_id = Column(Integer, ForeignKey("receipt_items.id"), nullable=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    source_context = Column(String(40), nullable=False, default="after_purchase")
    status = Column(String(20), nullable=False, default="unreviewed")
    notes = Column(String(500), nullable=True)
    image_path = Column(String(1000), nullable=False)
    captured_at = Column(DateTime, nullable=True)
    ai_extracted_name = Column(String(255), nullable=True)
    ai_brand = Column(String(120), nullable=True)
    ai_size_label = Column(String(120), nullable=True)
    ai_unit = Column(String(40), nullable=True)
    ai_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_product_snapshot_product_id", "product_id"),
        Index("ix_product_snapshot_shopping_list_item_id", "shopping_list_item_id"),
        Index("ix_product_snapshot_receipt_item_id", "receipt_item_id"),
        Index("ix_product_snapshot_purchase_id", "purchase_id"),
        Index("ix_product_snapshot_status", "status"),
        Index("ix_product_snapshot_source_context", "source_context"),
    )


class ContributionEvent(Base):
    __tablename__ = "contribution_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(String(50), nullable=False)
    subject_type = Column(String(50), nullable=True)
    subject_id = Column(Integer, nullable=True)
    status = Column(String(30), nullable=False, default="finalized")
    points = Column(Integer, nullable=False, default=0)
    description = Column(String(500), nullable=False)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_contribution_event_user_id", "user_id"),
        Index("ix_contribution_event_type", "event_type"),
        Index("ix_contribution_event_created_at", "created_at"),
    )


class AccessLink(Base):
    __tablename__ = "access_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    purpose = Column(String(40), nullable=False)  # shopping_helper, login_qr
    token_hash = Column(String(255), nullable=False, unique=True)
    metadata_json = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_access_link_purpose", "purpose"),
        Index("ix_access_link_expires_at", "expires_at"),
    )


class TrustedDevice(Base):
    __tablename__ = "trusted_devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    scope = Column(String(30), nullable=False, default="shared_household")
    status = Column(String(20), nullable=False, default="active")  # active, revoked
    token_hash = Column(String(255), nullable=False, unique=True)
    linked_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_trusted_device_status", "status"),
        Index("ix_trusted_device_linked_user_id", "linked_user_id"),
    )


class DevicePairingSession(Base):
    __tablename__ = "device_pairing_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pairing_token_hash = Column(String(255), nullable=False, unique=True)
    device_name = Column(String(120), nullable=False)
    scope = Column(String(30), nullable=False, default="shared_household")
    status = Column(String(20), nullable=False, default="pending")  # pending, approved, rejected, claimed
    created_by_device = Column(String(255), nullable=True)
    approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    trusted_device_id = Column(Integer, ForeignKey("trusted_devices.id"), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    approved_at = Column(DateTime, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_device_pairing_status", "status"),
        Index("ix_device_pairing_expires_at", "expires_at"),
    )


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

        inventory_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(inventory)"))
        }
        if "is_active_window" not in inventory_columns:
            conn.execute(text("ALTER TABLE inventory ADD COLUMN is_active_window BOOLEAN NOT NULL DEFAULT 1"))
        if "manual_low" not in inventory_columns:
            conn.execute(text("ALTER TABLE inventory ADD COLUMN manual_low BOOLEAN NOT NULL DEFAULT 0"))

        product_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(products)"))
        }
        if "raw_name" not in product_columns:
            conn.execute(text("ALTER TABLE products ADD COLUMN raw_name VARCHAR(255)"))
        if "display_name" not in product_columns:
            conn.execute(text("ALTER TABLE products ADD COLUMN display_name VARCHAR(255)"))
        if "brand" not in product_columns:
            conn.execute(text("ALTER TABLE products ADD COLUMN brand VARCHAR(120)"))
        if "size" not in product_columns:
            conn.execute(text("ALTER TABLE products ADD COLUMN size VARCHAR(80)"))
        if "default_unit" not in product_columns:
            conn.execute(text("ALTER TABLE products ADD COLUMN default_unit VARCHAR(40)"))
        if "default_size_label" not in product_columns:
            conn.execute(text("ALTER TABLE products ADD COLUMN default_size_label VARCHAR(120)"))
        if "enrichment_confidence" not in product_columns:
            conn.execute(text("ALTER TABLE products ADD COLUMN enrichment_confidence FLOAT"))
        if "enriched_at" not in product_columns:
            conn.execute(text("ALTER TABLE products ADD COLUMN enriched_at DATETIME"))
        if "review_state" not in product_columns:
            conn.execute(text("ALTER TABLE products ADD COLUMN review_state VARCHAR(20) DEFAULT 'pending'"))
        if "reviewed_at" not in product_columns:
            conn.execute(text("ALTER TABLE products ADD COLUMN reviewed_at DATETIME"))
        if "reviewed_by_id" not in product_columns:
            conn.execute(text("ALTER TABLE products ADD COLUMN reviewed_by_id INTEGER"))

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
        if "avatar_emoji" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN avatar_emoji VARCHAR(16)"))
        if "password_hash" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
        purchase_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(purchases)"))
        }
        if "domain" not in purchase_columns:
            conn.execute(text("ALTER TABLE purchases ADD COLUMN domain VARCHAR(30) NOT NULL DEFAULT 'grocery'"))
        if "transaction_type" not in purchase_columns:
            conn.execute(text("ALTER TABLE purchases ADD COLUMN transaction_type VARCHAR(20) NOT NULL DEFAULT 'purchase'"))
        if "refund_reason" not in purchase_columns:
            conn.execute(text("ALTER TABLE purchases ADD COLUMN refund_reason VARCHAR(40)"))
        if "refund_note" not in purchase_columns:
            conn.execute(text("ALTER TABLE purchases ADD COLUMN refund_note VARCHAR(500)"))
        if "default_spending_domain" not in purchase_columns:
            conn.execute(text("ALTER TABLE purchases ADD COLUMN default_spending_domain VARCHAR(30) NOT NULL DEFAULT 'grocery'"))
        if "default_budget_category" not in purchase_columns:
            conn.execute(text("ALTER TABLE purchases ADD COLUMN default_budget_category VARCHAR(40) NOT NULL DEFAULT 'grocery'"))
        conn.execute(text("""
            UPDATE purchases
            SET transaction_type = CASE
                WHEN COALESCE(NULLIF(TRIM(transaction_type), ''), '') = '' THEN 'purchase'
                WHEN LOWER(TRIM(transaction_type)) = 'refund' THEN 'refund'
                ELSE 'purchase'
            END
        """))
        conn.execute(text("""
            UPDATE purchases
            SET refund_reason = NULL,
                refund_note = NULL
            WHERE transaction_type <> 'refund'
        """))
        conn.execute(text("""
            UPDATE purchases
            SET default_spending_domain = CASE
                WHEN COALESCE(NULLIF(TRIM(default_spending_domain), ''), '') = ''
                    THEN COALESCE(NULLIF(TRIM(domain), ''), 'grocery')
                WHEN default_spending_domain = 'grocery' AND domain <> 'grocery'
                    THEN COALESCE(NULLIF(TRIM(domain), ''), 'grocery')
                ELSE default_spending_domain
            END
        """))
        conn.execute(text("""
            UPDATE purchases
            SET default_budget_category = CASE
                WHEN default_spending_domain = 'grocery' THEN 'grocery'
                WHEN default_spending_domain = 'restaurant' THEN 'dining'
                WHEN default_spending_domain = 'event' THEN 'events'
                WHEN default_spending_domain = 'general_expense' THEN 'other'
                ELSE 'other'
            END
            WHERE COALESCE(NULLIF(TRIM(default_budget_category), ''), '') = ''
               OR (default_budget_category = 'grocery' AND default_spending_domain <> 'grocery')
               OR (default_budget_category = 'other' AND default_spending_domain IN ('restaurant', 'event'))
        """))

        receipt_item_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(receipt_items)"))
        } if "receipt_items" in {
            row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        } else set()
        if receipt_item_columns and "spending_domain" not in receipt_item_columns:
            conn.execute(text("ALTER TABLE receipt_items ADD COLUMN spending_domain VARCHAR(30)"))
        if receipt_item_columns and "budget_category" not in receipt_item_columns:
            conn.execute(text("ALTER TABLE receipt_items ADD COLUMN budget_category VARCHAR(40)"))
        if receipt_item_columns and "unit" not in receipt_item_columns:
            conn.execute(text("ALTER TABLE receipt_items ADD COLUMN unit VARCHAR(40)"))
        if receipt_item_columns and "size_label" not in receipt_item_columns:
            conn.execute(text("ALTER TABLE receipt_items ADD COLUMN size_label VARCHAR(120)"))
        if receipt_item_columns:
            conn.execute(text("""
                UPDATE receipt_items
                SET unit = 'each'
                WHERE COALESCE(NULLIF(TRIM(unit), ''), '') = ''
            """))

        budget_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(budget)"))
        }
        if "domain" not in budget_columns:
            conn.execute(text("ALTER TABLE budget ADD COLUMN domain VARCHAR(30) NOT NULL DEFAULT 'grocery'"))
        if "budget_category" not in budget_columns:
            conn.execute(text("ALTER TABLE budget ADD COLUMN budget_category VARCHAR(40)"))
        budget_index_columns = []
        for index_row in conn.execute(text("PRAGMA index_list(budget)")):
            if int(index_row[2]) != 1:
                continue
            budget_index_columns = [
                info_row[2]
                for info_row in conn.execute(text(f"PRAGMA index_info('{index_row[1]}')"))
            ]
            if budget_index_columns:
                break
        if budget_index_columns == ["user_id", "month"]:
            conn.execute(text("""
                CREATE TABLE budget__migrated (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER REFERENCES users(id),
                    month VARCHAR(7) NOT NULL,
                    domain VARCHAR(30) NOT NULL DEFAULT 'grocery',
                    budget_category VARCHAR(40),
                    budget_amount FLOAT NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME,
                    CONSTRAINT uq_budget_user_month_domain UNIQUE (user_id, month, domain)
                )
            """))
            conn.execute(text("""
                INSERT INTO budget__migrated (id, user_id, month, domain, budget_category, budget_amount, created_at, updated_at)
                SELECT
                    id,
                    user_id,
                    month,
                    COALESCE(NULLIF(TRIM(domain), ''), 'grocery'),
                    budget_category,
                    budget_amount,
                    created_at,
                    updated_at
                FROM budget
            """))
            conn.execute(text("DROP TABLE budget"))
            conn.execute(text("ALTER TABLE budget__migrated RENAME TO budget"))
        if "budget_change_log" not in {
            row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }:
            conn.execute(text("""
                CREATE TABLE budget_change_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER REFERENCES users(id),
                    month VARCHAR(7) NOT NULL,
                    domain VARCHAR(30) NOT NULL DEFAULT 'grocery',
                    budget_category VARCHAR(40),
                    previous_amount FLOAT,
                    new_amount FLOAT NOT NULL,
                    changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX ix_budget_change_log_user_month ON budget_change_log (user_id, month)"))
            conn.execute(text("CREATE INDEX ix_budget_change_log_category ON budget_change_log (budget_category)"))
        if "password_reset_requested_at" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN password_reset_requested_at DATETIME"))
        if "session_version" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0"))

        contribution_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(contribution_events)"))
        } if "contribution_events" in {
            row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        } else set()
        if contribution_columns and "status" not in contribution_columns:
            conn.execute(text("ALTER TABLE contribution_events ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'finalized'"))

        shopping_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(shopping_list_items)"))
        } if "shopping_list_items" in {
            row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        } else set()
        if shopping_columns and "preferred_store" not in shopping_columns:
            conn.execute(text("ALTER TABLE shopping_list_items ADD COLUMN preferred_store VARCHAR(120)"))
        if shopping_columns and "manual_estimated_price" not in shopping_columns:
            conn.execute(text("ALTER TABLE shopping_list_items ADD COLUMN manual_estimated_price FLOAT"))
        if shopping_columns and "unit" not in shopping_columns:
            conn.execute(text("ALTER TABLE shopping_list_items ADD COLUMN unit VARCHAR(40)"))
        if shopping_columns and "size_label" not in shopping_columns:
            conn.execute(text("ALTER TABLE shopping_list_items ADD COLUMN size_label VARCHAR(120)"))
        if shopping_columns:
            conn.execute(text("""
                UPDATE shopping_list_items
                SET unit = 'each'
                WHERE COALESCE(NULLIF(TRIM(unit), ''), '') = ''
            """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS inventory_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                quantity_delta FLOAT NOT NULL DEFAULT 0,
                reason VARCHAR(50),
                user_id INTEGER,
                created_at DATETIME,
                FOREIGN KEY(product_id) REFERENCES products (id),
                FOREIGN KEY(user_id) REFERENCES users (id)
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_inventory_adjustment_product_id "
            "ON inventory_adjustments (product_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_inventory_adjustment_created_at "
            "ON inventory_adjustments (created_at)"
        ))


# ---------------------------------------------------------------------------
# Entry point for standalone initialization
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine, Session = initialize_database()
    logger.info("Database tables created.")
    logging.basicConfig(level=logging.INFO)
    engine, Session = initialize_database()
    logger.info("Database tables created.")
