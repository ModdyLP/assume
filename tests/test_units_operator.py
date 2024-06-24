# SPDX-FileCopyrightText: ASSUME Developers
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import datetime

import pandas as pd
import pytest
from dateutil import rrule as rr
from dateutil.relativedelta import relativedelta as rd
from mango import RoleAgent, create_container
from mango.util.clock import ExternalClock
from mango.util.termination_detection import tasks_complete_or_sleeping

from assume.common.forecasts import NaiveForecast
from assume.common.market_objects import MarketConfig, MarketProduct
from assume.common.units_operator import UnitsOperator
from assume.common.utils import datetime2timestamp
from assume.strategies.naive_strategies import NaiveSingleBidStrategy
from assume.units.demand import Demand
from assume.units.powerplant import PowerPlant

start = datetime(2020, 1, 1)
end = datetime(2020, 12, 2)


@pytest.fixture
async def units_operator() -> UnitsOperator:
    market_id = "EOM"
    marketconfig = MarketConfig(
        market_id=market_id,
        opening_hours=rr.rrule(rr.HOURLY, dtstart=start, until=end),
        opening_duration=rd(hours=1),
        market_mechanism="pay_as_clear",
        market_products=[MarketProduct(rd(hours=1), 1, rd(hours=1))],
    )
    clock = ExternalClock(0)
    container = await create_container(addr=("0.0.0.0", 9098), clock=clock)
    units_agent = RoleAgent(container, "test_operator")
    units_role = UnitsOperator(available_markets=[marketconfig])
    units_agent.add_role(units_role)

    index = pd.date_range(start=start, end=end + pd.Timedelta(hours=4), freq="1h")

    params_dict = {
        "bidding_strategies": {"EOM": NaiveSingleBidStrategy()},
        "technology": "energy",
        "unit_operator": "test_operator",
        "max_power": 1000,
        "min_power": 0,
        "forecaster": NaiveForecast(index, demand=1000),
    }
    unit = Demand("testdemand", index=index, **params_dict)
    await units_role.add_unit(unit)

    start_ts = datetime2timestamp(start)
    clock.set_time(start_ts)

    yield units_role

    end_ts = datetime2timestamp(end)
    clock.set_time(end_ts)
    await tasks_complete_or_sleeping(container)
    await container.shutdown()


async def test_set_unit_dispatch(units_operator: UnitsOperator):
    orderbook = [
        {
            "start_time": start,
            "end_time": start + rd(hours=1),
            "volume": 500,
            "accepted_volume": 500,
            "price": 1000,
            "accepted_price": 1000,
            "agent_id": "gen1",
            "unit_id": "testdemand",
            "only_hours": None,
        }
    ]
    marketconfig = units_operator.available_markets[0]

    assert units_operator.units["testdemand"].outputs["energy"].max() == 0

    units_operator.set_unit_dispatch(orderbook, marketconfig)
    assert units_operator.units["testdemand"].outputs["energy"].max() == 500


async def test_write_actual_dispatch(units_operator: UnitsOperator):
    units_operator.write_actual_dispatch("energy")
    assert units_operator.last_sent_dispatch["energy"] > 0
    assert units_operator.last_sent_dispatch["test"] == 0
    units_operator.write_actual_dispatch("test")
    assert units_operator.last_sent_dispatch["test"] > 0


async def test_formulate_bids(units_operator: UnitsOperator):
    marketconfig = units_operator.available_markets[0]
    from assume.common.utils import get_available_products

    products = get_available_products(marketconfig.market_products, start)
    orderbook = await units_operator.formulate_bids(marketconfig, products)
    assert len(orderbook) == 1

    assert orderbook[0]["volume"] == -1000
    assert orderbook[0]["price"] == 3000


@pytest.mark.require_learning
async def test_write_learning_params(units_operator: UnitsOperator):
    from assume.strategies.learning_advanced_orders import RLAdvancedOrderStrategy
    from assume.strategies.learning_strategies import RLStrategy

    marketconfig = units_operator.available_markets[0]
    start = datetime(2020, 1, 1)
    end = datetime(2020, 1, 2)
    index = pd.date_range(start=start, end=end + pd.Timedelta(hours=24), freq="1h")

    params_dict = {
        "bidding_strategies": {
            "EOM": RLAdvancedOrderStrategy(
                unit_id="testplant",
                learning_mode=True,
            )
        },
        "technology": "energy",
        "unit_operator": "test_operator",
        "max_power": 1000,
        "min_power": 0,
        "forecaster": NaiveForecast(index, powerplant=1000),
    }
    unit = PowerPlant("testplant", index=index, **params_dict)
    await units_operator.add_unit(unit)

    units_operator.learning_mode = True
    units_operator.learning_data = {"test": 1}

    units_operator.context.data.update(
        {
            "learning_output_agent_addr": "world",
            "learning_output_agent_id": "export_agent_1",
            "learning_agent_addr": "world_0",
            "learning_agent_id": "learning_agent",
        }
    )

    from assume.common.utils import get_available_products

    products = get_available_products(marketconfig.market_products, start)
    orderbook = await units_operator.formulate_bids(marketconfig, products)

    open_tasks = len(units_operator.context._scheduler._scheduled_tasks)

    units_operator.write_learning_params(orderbook, marketconfig)

    assert len(units_operator.context._scheduler._scheduled_tasks) == open_tasks + 2

    units_operator.units["testplant"].bidding_strategies[
        "EOM"
    ].bidding_strategies = RLStrategy(
        unit_id="testplant",
        learning_mode=True,
        observation_dimension=50,
        action_dimension=2,
    )

    units_operator.learning_data = {"test": 2}

    products = get_available_products(marketconfig.market_products, start)
    orderbook = await units_operator.formulate_bids(marketconfig, products)

    open_tasks = len(units_operator.context._scheduler._scheduled_tasks)

    units_operator.write_learning_params(orderbook, marketconfig)

    assert len(units_operator.context._scheduler._scheduled_tasks) == open_tasks + 2


async def test_get_actual_dispatch(units_operator: UnitsOperator):
    # GIVEN the first hour happened
    # the UnitOperator does not
    clock = units_operator.context._agent_context._container.clock

    last = clock.time
    clock.set_time(clock.time + 3600)
    # WHEN actual_dispatch is called
    market_dispatch, unit_dfs = units_operator.get_actual_dispatch("energy", last)
    # THEN resulting unit dispatch dataframe contains one row
    # which is for the current time - as we must know our current dispatch
    assert unit_dfs[0].index[0].timestamp() == clock.time
    assert len(unit_dfs[0]) == 1
    assert len(market_dispatch) == 0

    # WHEN another hour passes
    clock.set_time(clock.time + 3600)
    last = clock.time - 3600

    # THEN resulting unit dispatch dataframe contains only one row with current dispatch
    market_dispatch, unit_dfs = units_operator.get_actual_dispatch("energy", last)
    assert unit_dfs[0].index[0].timestamp() == clock.time
    assert len(unit_dfs[0]) == 1
    assert len(market_dispatch) == 0

    clock.set_time(clock.time + 3600)
    last = clock.time - 3600

    market_dispatch, unit_dfs = units_operator.get_actual_dispatch("energy", last)
    assert unit_dfs[0].index[0].timestamp() == clock.time
    assert len(unit_dfs[0]) == 1
    assert len(market_dispatch) == 0
