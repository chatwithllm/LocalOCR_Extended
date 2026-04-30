from src.backend.normalize_store_names import (
    canonicalize_store_name,
    is_payment_artifact,
)


def test_canonicalize_store_name_collapses_mcdonalds_store_numbers():
    assert canonicalize_store_name("Mcdonald's Restaurant #2674") == "McDonald's"
    assert canonicalize_store_name("MCDONALDS #38601") == "McDonald's"


def test_canonicalize_store_name_collapses_plain_mcdonalds_variants():
    assert canonicalize_store_name("mcdonald's") == "McDonald's"
    assert canonicalize_store_name("McDonalds") == "McDonald's"


def test_canonicalize_store_name_collapses_india_bazar_variants():
    assert canonicalize_store_name("India Bazar Inc") == "India Bazar"
    assert canonicalize_store_name("Indian Bazar") == "India Bazar"
    assert canonicalize_store_name("india bazar") == "India Bazar"


def test_canonicalize_store_name_collapses_india_bazar_typos():
    assert canonicalize_store_name("Indiaa Bazar") == "India Bazar"
    assert canonicalize_store_name("India Bazaar") == "India Bazar"
    assert canonicalize_store_name("Indian Bazaar") == "India Bazar"
    assert canonicalize_store_name("Indiaa Bazaar") == "India Bazar"


def test_canonicalize_store_name_collapses_costco_variants():
    assert canonicalize_store_name("Costco Wholesale") == "Costco"
    assert canonicalize_store_name("COSTCO WHOLESALE #1234") == "Costco"
    assert canonicalize_store_name("costco") == "Costco"
    assert canonicalize_store_name("COSTCO WHSE") == "Costco"


def test_canonicalize_store_name_keeps_costco_subbrands_distinct():
    # Tire Center / Gas are separate business units that show up under
    # their own names on receipts — don't collapse them into "Costco".
    assert canonicalize_store_name("Costco Tire Center") != "Costco"
    assert canonicalize_store_name("Costco Gas") != "Costco"


def test_canonicalize_store_name_keeps_other_stores_normalized():
    assert canonicalize_store_name("aes indiana") == "Aes Indiana"
    assert canonicalize_store_name("CVS pharmacy") == "CVS Pharmacy"


def test_is_payment_artifact_detects_credit_card_phrases():
    assert is_payment_artifact("CHASE CREDIT CRD AUTO-PMT")
    assert is_payment_artifact("Capital One AutoPay")
    assert is_payment_artifact("Discover Card Bill Payment")
    assert is_payment_artifact("Citi Credit Card Payment")
    assert is_payment_artifact("WELLS FARGO ONLINE PAYMENT")


def test_is_payment_artifact_detects_brand_only_rows():
    assert is_payment_artifact("Chase Sapphire")
    assert is_payment_artifact("American Express")
    assert is_payment_artifact("Capital One")
    assert is_payment_artifact("Discover Card")


def test_is_payment_artifact_detects_fees_and_interest():
    assert is_payment_artifact("Interest Charged on Purchases")
    assert is_payment_artifact("Late Fee")
    assert is_payment_artifact("Annual Fee")
    assert is_payment_artifact("Finance Charge")


def test_is_payment_artifact_detects_ach_and_bank_codes():
    assert is_payment_artifact("ACH PAYMENT DES:VERIZON")
    assert is_payment_artifact("WEBPAY DES:UTILITIES ID:ABC12345")
    assert is_payment_artifact("Wire Transfer Out")
    assert is_payment_artifact("Zelle to John")


def test_is_payment_artifact_detects_scheduled_and_check_transfers():
    assert is_payment_artifact("Online Scheduled Payment From Chk 4517")
    assert is_payment_artifact("Online Scheduled Payment To Crd 2029 Confirmation# Xxxxx01139")
    assert is_payment_artifact("Scheduled Payment To Crd 1234")
    assert is_payment_artifact("Transfer From Chk 0001")
    assert is_payment_artifact("Conf# ABCD1234")


def test_is_payment_artifact_detects_thank_you_payment_acks():
    assert is_payment_artifact("Payment - Thank You")
    assert is_payment_artifact("Payment Thank You-Mobile")
    assert is_payment_artifact("Thank You For Your Payment")
    assert is_payment_artifact("Online Payment, Thank You")


def test_is_payment_artifact_passes_real_merchants():
    assert not is_payment_artifact("Costco Wholesale")
    assert not is_payment_artifact("Kroger")
    assert not is_payment_artifact("India Bazar")
    assert not is_payment_artifact("McDonald's")
    assert not is_payment_artifact("AES Indiana")
    assert not is_payment_artifact("CVS Pharmacy")
    assert not is_payment_artifact("Target")


def test_is_payment_artifact_handles_empty_input():
    assert not is_payment_artifact("")
    assert not is_payment_artifact(None)
