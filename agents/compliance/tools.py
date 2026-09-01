MIN_TRUST_SCORE = 0.6
APPROVED_TERMS = {"net-15", "net-30", "net-60", "prepaid"}


def check_trust_score(trust_score: float) -> bool:
    return trust_score >= MIN_TRUST_SCORE


def check_terms(terms: str) -> bool:
    return terms in APPROVED_TERMS


def check_price(unit_price: float, max_approved_price: float | None) -> bool:
    if max_approved_price is None:
        return True
    return unit_price <= max_approved_price