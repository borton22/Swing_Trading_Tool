# src/risk_manager.py

def calculate_position_size(capital: float, risk_percent: float, entry: float, stop: float):
    """
    Calcule la taille de position basée sur le risque fixe.
    Ex: 20000$ capital, 0.5% risque (100$), stop à 5$ de distance -> 20 actions.
    """
    if entry <= stop:
        return 0, 0, 0
    
    risk_amount = capital * (risk_percent / 100)
    risk_per_share = entry - stop
    
    if risk_per_share <= 0:
        return 0, 0, 0
        
    num_shares = int(risk_amount / risk_per_share)
    total_cost = num_shares * entry
    
    return num_shares, risk_amount, total_cost