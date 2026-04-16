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
    google_sub = Column(String(255), nullable=True, unique=True)  # Google stable user ID
    google_email = Column(String(255), nullable=True)             # Google account email (display)
    active_ai_model_config_id = Column(Integer, ForeignKey("ai_model_configs.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    purchases = relationship("Purchase", back_populates="user")
    budgets = relationship("Budget", back_populates="user")
    active_ai_model = relationship("AIModelConfig", foreign_keys=[active_ai_model_config_id])


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


class BillMeta(Base):
    """Sidecar metadata for household bill purchases."""

    __tablename__ = "bill_meta"

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=False, unique=True)
    provider_name = Column(String(255), nullable=True)
    provider_type = Column(String(60), nullable=True)
    service_types = Column(Text, nullable=True)
    account_label = Column(String(120), nullable=True)
    provider_id = Column(Integer, ForeignKey("bill_providers.id"), nullable=True)
    service_line_id = Column(Integer, ForeignKey("bill_service_lines.id"), nullable=True)
    service_period_start = Column(Date, nullable=True)
    service_period_end = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    billing_cycle_month = Column(String(7), nullable=True)
    billing_cycle = Column(String(20), nullable=False, default="monthly")
    planning_month = Column(String(7), nullable=True)
    is_recurring = Column(Boolean, nullable=False, default=True)
    auto_pay = Column(Boolean, nullable=False, default=False)
    payment_status = Column(String(20), nullable=False, default="upcoming")
    payment_confirmed_at = Column(DateTime, nullable=True)
    payment_confirmed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_bill_meta_purchase_id", "purchase_id"),
        Index("ix_bill_meta_billing_cycle_month", "billing_cycle_month"),
        Index("ix_bill_meta_planning_month", "planning_month"),
        Index("ix_bill_meta_payment_status", "payment_status"),
        Index("ix_bill_meta_provider_name", "provider_name"),
    )

    purchase = relationship("Purchase", backref="bill_meta_record", uselist=False)
    provider = relationship("BillProvider", back_populates="bill_meta_records")
    service_line = relationship("BillServiceLine", back_populates="bill_meta_records")


class BillProvider(Base):
    """Canonical provider identity for recurring household bills."""

    __tablename__ = "bill_providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canonical_name = Column(String(255), nullable=False)
    normalized_key = Column(String(255), nullable=False, unique=True)
    provider_type_hint = Column(String(60), nullable=True)
    provider_category = Column(String(30), nullable=False, default="other")
    preferred_contact_method = Column(String(20), nullable=True)
    payment_handle = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_bill_providers_normalized_key", "normalized_key"),
        Index("ix_bill_providers_canonical_name", "canonical_name"),
    )

    service_lines = relationship("BillServiceLine", back_populates="provider")
    bill_meta_records = relationship("BillMeta", back_populates="provider")


class BillServiceLine(Base):
    """Canonical provider service line such as electricity, water, or gas."""

    __tablename__ = "bill_service_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(Integer, ForeignKey("bill_providers.id"), nullable=False)
    service_type = Column(String(60), nullable=True)
    account_label = Column(String(120), nullable=True)
    preferred_payment_method = Column(String(20), nullable=True)
    expected_payment_day = Column(Integer, nullable=True)
    planning_month_rule = Column(String(30), nullable=True)
    typical_amount_min = Column(Float, nullable=True)
    typical_amount_max = Column(Float, nullable=True)
    normalized_key = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_bill_service_lines_provider_id", "provider_id"),
        Index("ix_bill_service_lines_normalized_key", "normalized_key"),
    )

    provider = relationship("BillProvider", back_populates="service_lines")
    bill_meta_records = relationship("BillMeta", back_populates="service_line")


class CashTransaction(Base):
    __tablename__ = "cash_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=False, unique=True)
    service_line_id = Column(Integer, ForeignKey("bill_service_lines.id"), nullable=False)
    planning_month = Column(String(7), nullable=False)
    transaction_date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    payment_method = Column(String(20), nullable=False, default="cash")
    transfer_reference = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    snapshot_id = Column(Integer, ForeignKey("product_snapshots.id"), nullable=True)
    status = Column(String(20), nullable=False, default="paid")
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_cash_transactions_service_line_id", "service_line_id"),
        Index("ix_cash_transactions_planning_month", "planning_month"),
        Index("ix_cash_transactions_transaction_date", "transaction_date"),
    )

    purchase = relationship("Purchase", backref="cash_transaction_record", uselist=False)
    service_line = relationship("BillServiceLine")
    snapshot = relationship("ProductSnapshot")
    created_by = relationship("User")


class BillAllocation(Base):
    """Link a single bill purchase to multiple service lines with specific amounts."""
    __tablename__ = "bill_allocations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=False)
    service_line_id = Column(Integer, ForeignKey("bill_service_lines.id"), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow)


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


class ShoppingSession(Base):
    """A shopping trip with a lifecycle: active → ready_to_bill → closed.

    Exactly one non-closed session is "current" at any time; that is where
    new items land and what the shopping page renders. Finalizing snapshots
    the estimated and actual totals onto the session so closed trips can be
    reviewed later.
    """

    __tablename__ = "shopping_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=True)
    status = Column(String(20), nullable=False, default="active")
    store_hint = Column(String(120), nullable=True)
    estimated_total_snapshot = Column(Float, nullable=True)
    actual_total_snapshot = Column(Float, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    closed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_shopping_sessions_status", "status"),
    )


class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    shopping_session_id = Column(Integer, ForeignKey("shopping_sessions.id"), nullable=True)
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
    actual_price = Column(Float, nullable=True)  # per-unit price actually paid, entered in Ready to Bill
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_shopping_list_status", "status"),
        Index("ix_shopping_list_user_id", "user_id"),
        Index("ix_shopping_list_product_id", "product_id"),
        Index("ix_shopping_list_items_shopping_session_id", "shopping_session_id"),
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
    file_hash = Column(String(64), nullable=True, index=True)  # SHA-256 hash for deduplication
    error_message = Column(Text, nullable=True)  # Store OCR/validation failure reason
    retry_count = Column(Integer, default=0)  # Track reprocess attempts
    last_reprocessed_at = Column(DateTime, nullable=True)  # Timestamp of last retry
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    service_name = Column(String(50), nullable=False)  # "gemini", "ollama"
    date = Column(Date, nullable=False)
    model_config_id = Column(Integer, ForeignKey("ai_model_configs.id"), nullable=True)
    request_count = Column(Integer, nullable=False, default=0)
    token_count = Column(Integer, nullable=False, default=0)
    prompt_token_count = Column(Integer, nullable=False, default=0)
    completion_token_count = Column(Integer, nullable=False, default=0)
    estimated_cost_usd = Column(Float, nullable=False, default=0.0)
    total_latency_ms = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("service_name", "date", name="uq_api_usage_per_day"),
    )


class AIModelConfig(Base):
    __tablename__ = "ai_model_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    provider = Column(String(40), nullable=False)
    model_string = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    price_tier = Column(String(20), nullable=False, default="free")
    is_enabled = Column(Boolean, nullable=False, default=True)
    is_visible = Column(Boolean, nullable=False, default=True)
    credential_mode = Column(String(20), nullable=False, default="env")
    api_key_encrypted = Column(Text, nullable=True)
    base_url = Column(String(255), nullable=True)
    supports_vision = Column(Boolean, nullable=False, default=True)
    supports_pdf = Column(Boolean, nullable=False, default=False)
    supports_json_mode = Column(Boolean, nullable=False, default=False)
    supports_image_input = Column(Boolean, nullable=False, default=True)
    input_cost_per_million = Column(Float, nullable=True)
    output_cost_per_million = Column(Float, nullable=True)
    sort_order = Column(Integer, nullable=False, default=100)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("provider", "model_string", name="uq_ai_model_configs_provider_model"),
        Index("ix_ai_model_configs_provider", "provider"),
        Index("ix_ai_model_configs_enabled_visible", "is_enabled", "is_visible"),
        Index("ix_ai_model_configs_sort_order", "sort_order"),
    )


class UserAIModelAccess(Base):
    __tablename__ = "user_ai_model_access"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    model_config_id = Column(Integer, ForeignKey("ai_model_configs.id"), nullable=False)
    unlocked_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "model_config_id", name="uq_user_ai_model_access"),
        Index("ix_user_ai_model_access_user_id", "user_id"),
        Index("ix_user_ai_model_access_model_id", "model_config_id"),
    )


class PlaidItem(Base):
    """One per-user Plaid Link connection (one institution = one item)."""

    __tablename__ = "plaid_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plaid_item_id = Column(String(255), nullable=False, unique=True)
    institution_id = Column(String(60), nullable=True)
    institution_name = Column(String(255), nullable=True)
    access_token_encrypted = Column(Text, nullable=False)
    accounts_json = Column(Text, nullable=True)  # last-known account list (name, mask, type)
    products = Column(String(255), nullable=True)  # comma-separated granted products
    transaction_cursor = Column(String(255), nullable=True)  # /transactions/sync cursor
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(40), nullable=True)  # "ok", "error", "login_required"
    last_sync_error = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active")  # active, disconnected, login_required
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_plaid_items_user_id", "user_id"),
        Index("ix_plaid_items_status", "status"),
    )


class PlaidStagedTransaction(Base):
    """Raw Plaid transactions awaiting user review before promotion to Purchase."""

    __tablename__ = "plaid_staged_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plaid_item_id = Column(Integer, ForeignKey("plaid_items.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plaid_transaction_id = Column(String(255), nullable=False, unique=True)
    plaid_account_id = Column(String(255), nullable=False)
    amount = Column(Float, nullable=False)  # positive = debit, negative = refund per Plaid convention
    iso_currency_code = Column(String(10), nullable=True)
    transaction_date = Column(Date, nullable=False)
    authorized_date = Column(Date, nullable=True)
    name = Column(String(500), nullable=True)
    merchant_name = Column(String(500), nullable=True)
    plaid_category_primary = Column(String(120), nullable=True)
    plaid_category_detailed = Column(String(255), nullable=True)
    plaid_category_json = Column(Text, nullable=True)  # full hierarchy as JSON array
    pending = Column(Boolean, nullable=False, default=False)
    suggested_receipt_type = Column(String(30), nullable=True)
    suggested_spending_domain = Column(String(30), nullable=True)
    suggested_budget_category = Column(String(40), nullable=True)
    status = Column(String(30), nullable=False, default="ready_to_import")
    # status values: ready_to_import, duplicate_flagged, skipped_pending, confirmed, dismissed
    duplicate_purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=True)
    confirmed_purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    dismissed_at = Column(DateTime, nullable=True)
    raw_json = Column(Text, nullable=False)  # full Plaid transaction payload for audit
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_plaid_staged_user_id", "user_id"),
        Index("ix_plaid_staged_status", "status"),
        Index("ix_plaid_staged_item_id", "plaid_item_id"),
        Index("ix_plaid_staged_account_id", "plaid_account_id"),
        Index("ix_plaid_staged_date", "transaction_date"),
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
    _seed_default_ai_model_configs(Session)
    logger.info("Database schema initialized successfully.")
    return engine, Session


def _ensure_runtime_columns(engine):
    """Add a few backward-compatible columns for SQLite dev databases."""
    with engine.begin() as conn:
        if engine.dialect.name != "sqlite":
            return

        existing_tables = {
            row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }

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
        if "active_ai_model_config_id" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN active_ai_model_config_id INTEGER"))
        if "ai_model_configs" in existing_tables:
            ai_model_columns = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(ai_model_configs)"))
            }
            if "input_cost_per_million" not in ai_model_columns:
                conn.execute(text("ALTER TABLE ai_model_configs ADD COLUMN input_cost_per_million FLOAT"))
            if "output_cost_per_million" not in ai_model_columns:
                conn.execute(text("ALTER TABLE ai_model_configs ADD COLUMN output_cost_per_million FLOAT"))
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
        if "api_usage" in existing_tables:
            api_usage_columns = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(api_usage)"))
            }
            if "model_config_id" not in api_usage_columns:
                conn.execute(text("ALTER TABLE api_usage ADD COLUMN model_config_id INTEGER"))
            if "prompt_token_count" not in api_usage_columns:
                conn.execute(text("ALTER TABLE api_usage ADD COLUMN prompt_token_count INTEGER NOT NULL DEFAULT 0"))
            if "completion_token_count" not in api_usage_columns:
                conn.execute(text("ALTER TABLE api_usage ADD COLUMN completion_token_count INTEGER NOT NULL DEFAULT 0"))
            if "estimated_cost_usd" not in api_usage_columns:
                conn.execute(text("ALTER TABLE api_usage ADD COLUMN estimated_cost_usd FLOAT NOT NULL DEFAULT 0"))
            if "total_latency_ms" not in api_usage_columns:
                conn.execute(text("ALTER TABLE api_usage ADD COLUMN total_latency_ms INTEGER NOT NULL DEFAULT 0"))
            if "last_used_at" not in api_usage_columns:
                conn.execute(text("ALTER TABLE api_usage ADD COLUMN last_used_at DATETIME"))

        if "bill_meta" not in existing_tables:
            conn.execute(text("""
                CREATE TABLE bill_meta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    purchase_id INTEGER NOT NULL UNIQUE REFERENCES purchases(id),
                    provider_name VARCHAR(255),
                    provider_type VARCHAR(60),
                    service_types TEXT,
                    account_label VARCHAR(120),
                    provider_id INTEGER REFERENCES bill_providers(id),
                    service_line_id INTEGER REFERENCES bill_service_lines(id),
                    service_period_start DATE,
                    service_period_end DATE,
                    due_date DATE,
                    billing_cycle_month VARCHAR(7),
                    billing_cycle VARCHAR(20) NOT NULL DEFAULT 'monthly',
                    planning_month VARCHAR(7),
                    is_recurring BOOLEAN NOT NULL DEFAULT 1,
                    auto_pay BOOLEAN NOT NULL DEFAULT 0,
                    payment_status VARCHAR(20) NOT NULL DEFAULT 'upcoming',
                    payment_confirmed_at DATETIME,
                    payment_confirmed_by_id INTEGER,
                    created_at DATETIME,
                    updated_at DATETIME,
                    FOREIGN KEY(purchase_id) REFERENCES purchases (id),
                    FOREIGN KEY(payment_confirmed_by_id) REFERENCES users (id))
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bill_meta_purchase_id ON bill_meta (purchase_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bill_meta_billing_cycle_month ON bill_meta (billing_cycle_month)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bill_meta_provider_name ON bill_meta (provider_name)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bill_meta_planning_month ON bill_meta (planning_month)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bill_meta_payment_status ON bill_meta (payment_status)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bill_meta_payment_status ON bill_meta (payment_status)"
            ))
        else:
            bill_meta_columns = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(bill_meta)"))
            }
            if "provider_name" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN provider_name VARCHAR(255)"))
            if "provider_type" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN provider_type VARCHAR(60)"))
            if "service_types" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN service_types TEXT"))
            if "account_label" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN account_label VARCHAR(120)"))
            if "provider_id" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN provider_id INTEGER"))
            if "service_line_id" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN service_line_id INTEGER"))
            if "service_period_start" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN service_period_start DATE"))
            if "service_period_end" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN service_period_end DATE"))
            if "due_date" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN due_date DATE"))
            if "billing_cycle_month" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN billing_cycle_month VARCHAR(7)"))
            if "billing_cycle" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN billing_cycle VARCHAR(20) NOT NULL DEFAULT 'monthly'"))
            if "planning_month" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN planning_month VARCHAR(7)"))
            if "is_recurring" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN is_recurring BOOLEAN NOT NULL DEFAULT 1"))
            if "auto_pay" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN auto_pay BOOLEAN NOT NULL DEFAULT 0"))
            if "created_at" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN created_at DATETIME"))
            if "updated_at" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN updated_at DATETIME"))
            if "payment_status" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN payment_status VARCHAR(20) NOT NULL DEFAULT 'upcoming'"))
            if "payment_confirmed_at" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN payment_confirmed_at DATETIME"))
            if "payment_confirmed_by_id" not in bill_meta_columns:
                conn.execute(text("ALTER TABLE bill_meta ADD COLUMN payment_confirmed_by_id INTEGER REFERENCES users(id)"))

            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bill_meta_purchase_id ON bill_meta (purchase_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bill_meta_billing_cycle_month ON bill_meta (billing_cycle_month)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bill_meta_provider_name ON bill_meta (provider_name)"
            ))

        if "bill_providers" not in existing_tables:
            conn.execute(text("""
                CREATE TABLE bill_providers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_name VARCHAR(255) NOT NULL,
                    normalized_key VARCHAR(255) NOT NULL UNIQUE,
                    provider_type_hint VARCHAR(60),
                    provider_category VARCHAR(30) NOT NULL DEFAULT 'other',
                    preferred_contact_method VARCHAR(20),
                    payment_handle VARCHAR(255),
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
        if "bill_service_lines" not in existing_tables:
            conn.execute(text("""
                CREATE TABLE bill_service_lines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id INTEGER NOT NULL REFERENCES bill_providers(id),
                    service_type VARCHAR(60),
                    account_label VARCHAR(120),
                    preferred_payment_method VARCHAR(20),
                    expected_payment_day INTEGER,
                    planning_month_rule VARCHAR(30),
                    typical_amount_min FLOAT,
                    typical_amount_max FLOAT,
                    normalized_key VARCHAR(255) NOT NULL UNIQUE,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
        bill_provider_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(bill_providers)"))
        } if "bill_providers" in existing_tables else {
            "id",
            "canonical_name",
            "normalized_key",
            "provider_type_hint",
            "provider_category",
            "preferred_contact_method",
            "payment_handle",
            "is_active",
            "created_at",
            "updated_at",
        }
        if "provider_category" not in bill_provider_columns:
            conn.execute(text("ALTER TABLE bill_providers ADD COLUMN provider_category VARCHAR(30) NOT NULL DEFAULT 'other'"))
        if "preferred_contact_method" not in bill_provider_columns:
            conn.execute(text("ALTER TABLE bill_providers ADD COLUMN preferred_contact_method VARCHAR(20)"))
        if "payment_handle" not in bill_provider_columns:
            conn.execute(text("ALTER TABLE bill_providers ADD COLUMN payment_handle VARCHAR(255)"))

        bill_service_line_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(bill_service_lines)"))
        } if "bill_service_lines" in existing_tables else {
            "id",
            "provider_id",
            "service_type",
            "account_label",
            "preferred_payment_method",
            "expected_payment_day",
            "planning_month_rule",
            "typical_amount_min",
            "typical_amount_max",
            "normalized_key",
            "is_active",
            "created_at",
            "updated_at",
        }
        if "preferred_payment_method" not in bill_service_line_columns:
            conn.execute(text("ALTER TABLE bill_service_lines ADD COLUMN preferred_payment_method VARCHAR(20)"))
        if "expected_payment_day" not in bill_service_line_columns:
            conn.execute(text("ALTER TABLE bill_service_lines ADD COLUMN expected_payment_day INTEGER"))
        if "planning_month_rule" not in bill_service_line_columns:
            conn.execute(text("ALTER TABLE bill_service_lines ADD COLUMN planning_month_rule VARCHAR(30)"))
        if "typical_amount_min" not in bill_service_line_columns:
            conn.execute(text("ALTER TABLE bill_service_lines ADD COLUMN typical_amount_min FLOAT"))
        if "typical_amount_max" not in bill_service_line_columns:
            conn.execute(text("ALTER TABLE bill_service_lines ADD COLUMN typical_amount_max FLOAT"))

        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_bill_providers_normalized_key ON bill_providers (normalized_key)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_bill_providers_canonical_name ON bill_providers (canonical_name)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_bill_service_lines_provider_id ON bill_service_lines (provider_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_bill_service_lines_normalized_key ON bill_service_lines (normalized_key)"
        ))

        conn.execute(text("""
            INSERT OR IGNORE INTO bill_providers (canonical_name, normalized_key, provider_type_hint, is_active, created_at, updated_at)
            SELECT
                TRIM(provider_name) AS canonical_name,
                LOWER(TRIM(provider_name)) AS normalized_key,
                NULLIF(LOWER(TRIM(provider_type)), '') AS provider_type_hint,
                1,
                COALESCE(created_at, CURRENT_TIMESTAMP),
                COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM bill_meta
            WHERE COALESCE(NULLIF(TRIM(provider_name), ''), '') <> ''
        """))
        conn.execute(text("""
            UPDATE bill_meta
            SET provider_id = (
                SELECT bp.id
                FROM bill_providers bp
                WHERE bp.normalized_key = LOWER(TRIM(bill_meta.provider_name))
                LIMIT 1
            )
            WHERE provider_id IS NULL
              AND COALESCE(NULLIF(TRIM(provider_name), ''), '') <> ''
        """))
        conn.execute(text("""
            INSERT OR IGNORE INTO bill_service_lines (provider_id, service_type, account_label, normalized_key, is_active, created_at, updated_at)
            SELECT
                bm.provider_id,
                NULLIF(LOWER(TRIM(COALESCE(bm.provider_type, 'other'))), ''),
                NULLIF(TRIM(bm.account_label), ''),
                LOWER(
                    TRIM(COALESCE(bm.provider_name, 'unknown'))
                    || '::' || TRIM(COALESCE(bm.provider_type, 'other'))
                    || '::' || TRIM(COALESCE(bm.account_label, 'default'))
                ),
                1,
                COALESCE(bm.created_at, CURRENT_TIMESTAMP),
                COALESCE(bm.updated_at, CURRENT_TIMESTAMP)
            FROM bill_meta bm
            WHERE bm.provider_id IS NOT NULL
        """))
        conn.execute(text("""
            UPDATE bill_meta
            SET service_line_id = (
                SELECT bsl.id
                FROM bill_service_lines bsl
                WHERE bsl.normalized_key = LOWER(
                    TRIM(COALESCE(bill_meta.provider_name, 'unknown'))
                    || '::' || TRIM(COALESCE(bill_meta.provider_type, 'other'))
                    || '::' || TRIM(COALESCE(bill_meta.account_label, 'default'))
                )
                LIMIT 1
            )
            WHERE service_line_id IS NULL
              AND provider_id IS NOT NULL
        """))
        conn.execute(text("""
            UPDATE bill_providers
            SET provider_category = CASE
                WHEN LOWER(COALESCE(provider_type_hint, '')) IN ('internet', 'electricity', 'gas', 'water', 'trash', 'utility', 'utilities', 'insurance', 'housing')
                    THEN 'utility'
                WHEN LOWER(COALESCE(provider_type_hint, '')) IN ('subscription', 'streaming', 'phone')
                    THEN 'subscription'
                ELSE COALESCE(NULLIF(provider_category, ''), 'other')
            END
        """))

        if "cash_transactions" not in existing_tables:
            conn.execute(text("""
                CREATE TABLE cash_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    purchase_id INTEGER NOT NULL UNIQUE REFERENCES purchases(id),
                    service_line_id INTEGER NOT NULL REFERENCES bill_service_lines(id),
                    planning_month VARCHAR(7) NOT NULL,
                    transaction_date DATE NOT NULL,
                    amount FLOAT NOT NULL,
                    payment_method VARCHAR(20) NOT NULL DEFAULT 'cash',
                    transfer_reference VARCHAR(255),
                    notes TEXT,
                    snapshot_id INTEGER REFERENCES product_snapshots(id),
                    status VARCHAR(20) NOT NULL DEFAULT 'paid',
                    created_by_id INTEGER REFERENCES users(id),
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_cash_transactions_service_line_id ON cash_transactions (service_line_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_cash_transactions_planning_month ON cash_transactions (planning_month)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_cash_transactions_transaction_date ON cash_transactions (transaction_date)"
        ))
        conn.execute(text("""
            UPDATE cash_transactions
            SET status = 'upcoming',
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'paid'
              AND DATE(transaction_date) > DATE('now')
        """))
        conn.execute(text("""
            UPDATE bill_service_lines
            SET planning_month_rule = 'paid_date_month',
                updated_at = CURRENT_TIMESTAMP
            WHERE provider_id IN (
                SELECT id
                FROM bill_providers
                WHERE provider_category = 'personal_service'
            )
              AND COALESCE(expected_payment_day, 0) = 0
              AND COALESCE(NULLIF(TRIM(planning_month_rule), ''), 'due_date_month') = 'due_date_month'
        """))

        receipt_item_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(receipt_items)"))
        } if "receipt_items" in existing_tables else set()
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
        if "google_sub" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN google_sub VARCHAR(255)"))
        if "google_email" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN google_email VARCHAR(255)"))

        contribution_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(contribution_events)"))
        } if "contribution_events" in existing_tables else set()
        if contribution_columns and "status" not in contribution_columns:
            conn.execute(text("ALTER TABLE contribution_events ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'finalized'"))

        shopping_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(shopping_list_items)"))
        } if "shopping_list_items" in existing_tables else set()
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


def _seed_default_ai_model_configs(SessionFactory):
    """Seed a small default model catalog for Phase 1 without duplicating rows."""
    session = SessionFactory()
    try:
        seeded_models = [
            {
                "name": "Gemini Flash",
                "provider": "gemini",
                "model_string": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                "description": "Fast default OCR with PDF support.",
                "price_tier": "free",
                "is_enabled": bool((os.getenv("GEMINI_API_KEY") or "").strip()),
                "is_visible": True,
                "credential_mode": "env",
                "supports_vision": True,
                "supports_pdf": True,
                "supports_json_mode": True,
                "supports_image_input": True,
                "sort_order": 10,
            },
            {
                "name": "OpenAI Vision",
                "provider": "openai",
                "model_string": os.getenv("OPENAI_OCR_MODEL", "gpt-4.1-mini"),
                "description": "OpenAI-compatible OCR fallback for images and PDFs.",
                "price_tier": "premium",
                "is_enabled": bool((os.getenv("OPENAI_API_KEY") or "").strip()),
                "is_visible": True,
                "credential_mode": "env",
                "supports_vision": True,
                "supports_pdf": True,
                "supports_json_mode": True,
                "supports_image_input": True,
                "sort_order": 20,
            },
            {
                "name": "Ollama Vision",
                "provider": "ollama",
                "model_string": os.getenv("OLLAMA_MODEL", "llava:7b"),
                "description": "Local OCR via Ollama for self-hosted fallback.",
                "price_tier": "free",
                "is_enabled": True,
                "is_visible": True,
                "credential_mode": "no_key_required",
                "base_url": os.getenv("OLLAMA_ENDPOINT", "http://ollama:11434"),
                "supports_vision": True,
                "supports_pdf": False,
                "supports_json_mode": False,
                "supports_image_input": True,
                "sort_order": 30,
            },
            {
                "name": "OpenRouter Vision",
                "provider": "openrouter",
                "model_string": os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001"),
                "description": "OpenRouter-hosted OCR using an OpenAI-compatible API.",
                "price_tier": "premium",
                "is_enabled": bool((os.getenv("OPENROUTER_API_KEY") or "").strip()),
                "is_visible": True,
                "credential_mode": "env",
                "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                "supports_vision": True,
                "supports_pdf": True,
                "supports_json_mode": True,
                "supports_image_input": True,
                "sort_order": 40,
            },
            {
                "name": "Anthropic Vision",
                "provider": "anthropic",
                "model_string": os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
                "description": "Anthropic vision OCR support scaffold.",
                "price_tier": "premium",
                "is_enabled": bool((os.getenv("ANTHROPIC_API_KEY") or "").strip()),
                "is_visible": True,
                "credential_mode": "env",
                "supports_vision": True,
                "supports_pdf": True,
                "supports_json_mode": True,
                "supports_image_input": True,
                "sort_order": 50,
            },
        ]

        for payload in seeded_models:
            existing = (
                session.query(AIModelConfig)
                .filter_by(provider=payload["provider"], model_string=payload["model_string"])
                .first()
            )
            if existing:
                if existing.name != payload["name"]:
                    existing.name = payload["name"]
                if existing.description != payload["description"]:
                    existing.description = payload["description"]
                if existing.credential_mode != payload["credential_mode"]:
                    existing.credential_mode = payload["credential_mode"]
                if payload.get("base_url") and existing.base_url != payload["base_url"]:
                    existing.base_url = payload["base_url"]
                existing.supports_vision = payload["supports_vision"]
                existing.supports_pdf = payload["supports_pdf"]
                existing.supports_json_mode = payload["supports_json_mode"]
                existing.supports_image_input = payload["supports_image_input"]
                existing.sort_order = payload["sort_order"]
                if existing.is_enabled is False and payload["is_enabled"]:
                    existing.is_enabled = True
                if existing.is_visible is False:
                    existing.is_visible = True
                continue

            session.add(AIModelConfig(**payload))

        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to seed default AI model configs.")
    finally:
        session.close()


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
