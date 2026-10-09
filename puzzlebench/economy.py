"""Shared hint wallet: the economy that makes allocation decisions real.

A protocol-B run issues one wallet per run; every episode in the run spends
from it. If each episode had its own coins there would be no cross-puzzle
allocation problem and regret would degenerate to zero for answer-buyers.
"""


class Wallet:
    def __init__(self, balance: int) -> None:
        self.balance = balance
        self.spent = 0

    def try_spend(self, cost: int) -> bool:
        if cost > self.balance:
            return False
        self.balance -= cost
        self.spent += cost
        return True
