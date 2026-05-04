# server/scoring.py

def compute_score(underwriting: dict) -> int:
    """
    Compute a 0–100 investment score based on underwriting metrics.
    """

    roi = underwriting.get("roi", 0)
    cap_rate = underwriting.get("cap_rate", 0)
    cash_flow = underwriting.get("cash_flow", 0)
    ptr = underwriting.get("price_to_rent", 0)

    # Normalize values into weighted score components
    roi_score = min(max(roi * 10, 0), 40)          # ROI up to 4.0 → 40 points
    cap_score = min(max(cap_rate * 5, 0), 25)      # Cap rate up to 5% → 25 points
    cash_score = min(max(cash_flow / 50, 0), 25)   # $1250/mo → 25 points

    # Price-to-rent ratio (lower = better)
    if ptr > 0:
        ptr_score = min(max((1 / ptr) * 100, 0), 10)
    else:
        ptr_score = 0

    total = roi_score + cap_score + cash_score + ptr_score
    return int(min(max(total, 0), 100))
