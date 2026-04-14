from src.backend.normalize_store_names import canonicalize_store_name


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


def test_canonicalize_store_name_keeps_other_stores_normalized():
    assert canonicalize_store_name("aes indiana") == "Aes Indiana"
    assert canonicalize_store_name("CVS pharmacy") == "CVS Pharmacy"
