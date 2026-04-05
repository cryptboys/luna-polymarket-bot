from __future__ import annotations


class PnlCalculator:
    @staticmethod
    def calc_pnl_yes(entry_price: float, exit_price: float, shares: float) -> float:
        return shares * (exit_price - entry_price)

    @staticmethod
    def calc_pnl_no(entry_price: float, exit_price: float, shares: float) -> float:
        return shares * (entry_price - exit_price)

    @staticmethod
    def calc_pnl(side: str, entry_price: float, exit_price: float, shares: float) -> float:
        if side == "YES":
            return PnlCalculator.calc_pnl_yes(entry_price, exit_price, shares)
        return PnlCalculator.calc_pnl_no(entry_price, exit_price, shares)

    @staticmethod
    def calc_roi_yes(entry_price: float, exit_price: float) -> float:
        if entry_price <= 0:
            return 0.0
        return (exit_price - entry_price) / entry_price

    @staticmethod
    def calc_roi_no(entry_price: float, exit_price: float) -> float:
        if entry_price >= 1:
            return 0.0
        entry_cost = 1 - entry_price
        exit_value = 1 - exit_price
        return (exit_value - entry_cost) / entry_cost if entry_cost > 0 else 0.0

    @staticmethod
    def calc_roi(side: str, entry_price: float, exit_price: float) -> float:
        if side == "YES":
            return PnlCalculator.calc_roi_yes(entry_price, exit_price)
        return PnlCalculator.calc_roi_no(entry_price, exit_price)

    @staticmethod
    def calc_potential_payout_yes(entry_price: float, shares: float) -> float:
        return shares * (1.0 - entry_price)

    @staticmethod
    def calc_potential_payout_no(entry_price: float, shares: float) -> float:
        return shares * entry_price

    @staticmethod
    def calc_potential_payout(side: str, entry_price: float, shares: float) -> float:
        if side == "YES":
            return PnlCalculator.calc_potential_payout_yes(entry_price, shares)
        return PnlCalculator.calc_potential_payout_no(entry_price, shares)
