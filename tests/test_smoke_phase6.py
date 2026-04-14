import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date

os.environ["DATABASE_URL"] = "sqlite://"

@pytest.fixture
def session():
    from src.backend.initialize_database_schema import initialize_database
    _, SessionFactory = initialize_database()
    session = SessionFactory()
    yield session
    session.close()

def test_phase6_projections_analytical(session):
    from src.backend.initialize_database_schema import BillMeta, Purchase, User
    from src.backend.generate_bill_projections import generate_monthly_obligation_slots
    
    # 1. Setup history for "Internet Co" (Stable $50)
    for i in range(1, 4):
        p = Purchase(total_amount=50.0, date=date(2026, i, 10))
        session.add(p)
        session.flush()
        bm = BillMeta(
            purchase_id=p.id,
            provider_name="Internet Co",
            planning_month=f"2026-0{i}",
            is_recurring=True,
            due_date=date(2026, i, 25),
            payment_status="paid"
        )
        session.add(bm)

    # 2. Setup history for "Power Co" (Averages $100, one anomaly)
    # 2026-01: $100
    p1 = Purchase(total_amount=100.0, date=date(2026, 1, 15))
    session.add(p1)
    session.flush()
    session.add(BillMeta(purchase_id=p1.id, provider_name="Power Co", planning_month="2026-01", is_recurring=True))
    
    # 2026-02: $150 (30% difference from 100 is 130, so 150 is an anomaly)
    p2 = Purchase(total_amount=150.0, date=date(2026, 2, 15))
    session.add(p2)
    session.flush()
    session.add(BillMeta(purchase_id=p2.id, provider_name="Power Co", planning_month="2026-02", is_recurring=True))
    
    session.commit()

    # 3. Test April Projections (should have 2 projected slots)
    slots = generate_monthly_obligation_slots(session, "2026-04")
    
    internet_slot = next(s for s in slots if s["provider_name"] == "Internet Co")
    power_slot = next(s for s in slots if s["provider_name"] == "Power Co")
    
    assert internet_slot["amount"] == 50.0
    assert power_slot["amount"] == 125.0 # Average of 100 and 150
    assert power_slot["payment_status"] == "not_yet_entered"

    # 4. Test Missing Detection
    # If today is April 20th and Power Co usually arrives on the 15th
    with patch("src.backend.generate_bill_projections.datetime") as mock_dt:
        # Mocking datetime.now()
        mock_dt.now.return_value = datetime(2026, 4, 25)
        mock_dt.strftime = datetime.strftime
        
        slots_late = generate_monthly_obligation_slots(session, "2026-04")
        p_slot = next(s for s in slots_late if s["provider_name"] == "Power Co")
        assert p_slot["payment_status"] == "missing"

    # 5. Test Anomaly Surface in Actuals
    # Add an actual bill for April for Power Co that is huge
    p_huge = Purchase(total_amount=300.0, date=date(2026, 4, 15))
    session.add(p_huge)
    session.flush()
    session.add(BillMeta(purchase_id=p_huge.id, provider_name="Power Co", planning_month="2026-04", is_recurring=True))
    session.commit()

    slots_actual = generate_monthly_obligation_slots(session, "2026-04")
    p_actual = next(s for s in slots_actual if s["provider_name"] == "Power Co" and s["slot_type"] == "actual")
    
    assert p_actual["is_anomaly"] is True
    assert "higher" in p_actual["anomaly_reason"]


def test_phase6_projections_distinguish_service_lines_under_same_provider(session):
    from src.backend.initialize_database_schema import BillMeta, Purchase, BillProvider, BillServiceLine
    from src.backend.generate_bill_projections import generate_monthly_obligation_slots

    provider = BillProvider(canonical_name="Citizens Energy", normalized_key="citizens energy")
    session.add(provider)
    session.flush()

    water = BillServiceLine(provider_id=provider.id, service_type="water", account_label="HOME", normalized_key="citizens energy::water::home")
    gas = BillServiceLine(provider_id=provider.id, service_type="gas", account_label="HOME", normalized_key="citizens energy::gas::home")
    session.add_all([water, gas])
    session.flush()

    p_water = Purchase(total_amount=40.0, date=date(2026, 1, 12))
    p_gas = Purchase(total_amount=60.0, date=date(2026, 1, 14))
    session.add_all([p_water, p_gas])
    session.flush()

    session.add(BillMeta(
        purchase_id=p_water.id,
        provider_name="Citizens Energy",
        provider_type="water",
        account_label="HOME",
        service_line_id=water.id,
        planning_month="2026-01",
        is_recurring=True,
    ))
    session.add(BillMeta(
        purchase_id=p_gas.id,
        provider_name="Citizens Energy",
        provider_type="gas",
        account_label="HOME",
        service_line_id=gas.id,
        planning_month="2026-01",
        is_recurring=True,
    ))
    session.commit()

    slots = generate_monthly_obligation_slots(session, "2026-02")
    projected = [slot for slot in slots if slot["slot_type"] == "projected" and slot["provider_name"] == "Citizens Energy"]

    assert len(projected) == 2
    assert {slot["service_line_id"] for slot in projected} == {water.id, gas.id}
    assert {slot["provider_type"] for slot in projected} == {"water", "gas"}


def test_phase6_projections_respect_semiannual_cadence(session):
    from src.backend.initialize_database_schema import BillMeta, Purchase
    from src.backend.generate_bill_projections import generate_monthly_obligation_slots

    purchase = Purchase(total_amount=612.0, date=date(2026, 1, 10))
    session.add(purchase)
    session.flush()
    session.add(BillMeta(
        purchase_id=purchase.id,
        provider_name="Progressive Insurance",
        provider_type="insurance",
        planning_month="2026-01",
        billing_cycle="semiannual",
        is_recurring=True,
    ))
    session.commit()

    april_slots = generate_monthly_obligation_slots(session, "2026-04")
    assert not any(slot["provider_name"] == "Progressive Insurance" for slot in april_slots)

    july_slots = generate_monthly_obligation_slots(session, "2026-07")
    july_progressive = next(
        slot for slot in july_slots if slot["provider_name"] == "Progressive Insurance"
    )
    assert july_progressive["slot_type"] == "projected"
    assert july_progressive["billing_cycle"] == "semiannual"
