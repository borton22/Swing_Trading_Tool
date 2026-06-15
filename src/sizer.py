import math

def calculate_position_size(
    capital: float,
    risk_per_trade_pct: float,
    entry_price: float,
    stop_price: float
):
    if entry_price <= stop_price:
        return {
            "shares": 0,
            "risk_amount": 0,
            "total_cost": 0,
            "take_profit": 0,
            "potential_profit": 0
        }

    risk_amount = capital * risk_per_trade_pct

    risk_per_share = entry_price - stop_price

    shares = math.floor(risk_amount / risk_per_share)

    total_cost = shares * entry_price

    take_profit = entry_price + (risk_per_share * 2)

    potential_profit = shares * (take_profit - entry_price)

    return {
        "shares": shares,
        "risk_amount": round(shares * risk_per_share, 2),
        "total_cost": round(total_cost, 2),
        "risk_per_share": round(risk_per_share, 2),
        "take_profit": round(take_profit, 2),
        "potential_profit": round(potential_profit, 2)
    }