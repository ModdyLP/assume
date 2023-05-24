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
        unit_operator: str,
        technology: str,
        bidding_strategies: dict,
        index: pd.DatetimeIndex,
        max_power: float or pd.Series,
        min_power: float or pd.Series,
        node: str = "bus0",
        price: float or pd.Series = 3000.0,
        location: tuple[float, float] = (0.0, 0.0),
        **kwargs
    ):
        super().__init__(
            id=id,
            unit_operator=unit_operator,
            technology=technology,
            bidding_strategies=bidding_strategies,
            index=index,
            node=node,
        )

        self.max_power = max_power
        self.min_power = min_power
        self.price = price
        self.location = location
        self.total_power_output = []

    def reset(self):
        self.total_power_output = pd.Series(0, index=self.index)

    def calculate_operational_window(
        self,
        product_type: str,
        product_tuple: tuple,
    ) -> dict:
        start, end, only_hours = product_tuple
        start = pd.Timestamp(start)
        end = pd.Timestamp(end)
        """Calculate the operation window for the next time step."""
        if type(self.max_power) == pd.Series:
            bid_volume = self.max_power.loc[start]
        else:
            bid_volume = self.max_power

        if type(self.price) == pd.Series:
            bid_price = self.price.loc[start]
        else:
            bid_price = self.price

        return {"max_power": {"power": -bid_volume, "marginal_cost": bid_price}}

    def get_dispatch_plan(self, dispatch_plan, time_period):
        self.total_power_output.loc[time_period] = dispatch_plan["total_power"]
