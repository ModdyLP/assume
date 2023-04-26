import pandas as pd

from assume.strategies import BaseStrategy
from assume.units.base_unit import BaseUnit


class Demand(BaseUnit):
    """A demand unit.

    Attributes
    ----------
    id : str
        The ID of the unit.
    technology : str
        The technology of the unit.
    node : str
        The node of the unit.

    Methods
    -------
    calculate_operational_window(product)
        Calculate the operation window for the next time step.
    """

    def __init__(
        self,
        id: str,
        technology: str,
        bidding_strategies: dict,
        node: str = None,
        price: float or pd.Series = 3000.0,
        volume: float or pd.Series = 1000,
        index: pd.DatetimeIndex = None,
        location: tuple[float, float] = None,
        **kwargs
    ):
        super().__init__(
            id=id,
            technology=technology,
            node=node,
            bidding_strategies=bidding_strategies,
            index=index,
        )

        self.price = price
        self.volume = volume
        self.location = location
        self.total_power_output = []

    def reset(self):
        self.total_capacity = pd.Series(0.0, index=self.index)

    def calculate_operational_window(
        self, product_type: str, current_time: pd.Timestamp
    ) -> dict:
        """Calculate the operation window for the next time step."""
        if type(self.volume) == pd.Series:
            bid_volume = self.volume.loc[current_time]
        else:
            bid_volume = self.volume

        if type(self.price) == pd.Series:
            bid_price = self.price.loc[current_time]
        else:
            bid_price = self.price

        return {"max_power": {"power": -bid_volume, "marginal_cost": bid_price}}

    def calculate_bids(
        self,
        product_type,
        operational_window,
    ):
        return super().calculate_bids(
            unit=self,
            product_type=product_type,
            operational_window=operational_window,
        )
    
    def get_dispatch_plan(self, dispatch_plan, current_time):
        self.total_capacity.at[current_time] = dispatch_plan["total_capacity"]

    
