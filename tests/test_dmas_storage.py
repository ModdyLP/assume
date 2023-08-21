from datetime import datetime, timedelta

import pandas as pd
import pytest
from dateutil import rrule as rr

from assume.common.forecasts import NaiveForecast
from assume.common.market_objects import MarketConfig, MarketProduct
from assume.common.utils import get_available_products
from assume.strategies.dmas_storage import DmasStorageStrategy
from assume.strategies.naive_strategies import NaiveStrategy
from assume.units import PowerPlant, Storage

from .utils import get_test_prices


@pytest.fixture
def storage_unit() -> Storage:
    return Storage(
        id="Test_Storage",
        unit_operator="TestOperator",
        technology="TestTechnology",
        bidding_strategies={"energy": NaiveStrategy()},
        max_power_charge=100,
        max_power_discharge=100,
        max_volume=1000,
        efficiency_charge=0.9,
        efficiency_discharge=0.95,
        index=pd.date_range("2022-01-01", periods=4, freq="H"),
        ramp_down_charge=-50,
        ramp_down_discharge=50,
        ramp_up_charge=-60,
        ramp_up_discharge=60,
        variable_cost_charge=3,
        variable_cost_discharge=4,
        fixed_cost=1,
    )


@pytest.fixture
def storage_day() -> PowerPlant:
    periods = 48
    index = pd.date_range("2022-01-01", periods=periods, freq="H")

    prices = get_test_prices(periods)
    ff = NaiveForecast(
        index,
        availability=1,
        co2_price=prices["co2"],
        price_forecast=prices["power"],
    )
    return Storage(
        id="Test_Storage",
        unit_operator="TestOperator",
        technology="TestTechnology",
        bidding_strategies={"energy": NaiveStrategy()},
        max_power_charge=100,
        max_power_discharge=100,
        max_volume=1000,
        efficiency_charge=0.9,
        efficiency_discharge=0.95,
        index=index,
        ramp_down_charge=-50,
        ramp_down_discharge=50,
        ramp_up_charge=-60,
        ramp_up_discharge=60,
        variable_cost_charge=3,
        variable_cost_discharge=4,
        fixed_cost=1,
        forecaster=ff,
    )


def test_dmas_str_init(storage_unit):
    strategy = DmasStorageStrategy()
    hour_count = len(storage_unit.index)

    prices = get_test_prices()

    strategy.build_model(
        storage_unit,
        datetime(2022, 1, 1),
        hour_count,
    )


def test_dmas_calc(storage_unit):
    strategy = DmasStorageStrategy()
    hour_count = len(storage_unit.index) // 2

    mc = MarketConfig(
        "Test",
        rr.rrule(rr.HOURLY),
        timedelta(hours=1),
        "not needed",
        [MarketProduct(timedelta(hours=1), hour_count, timedelta(hours=0))],
        additional_fields=["exclusive_id"],
    )
    start = storage_unit.index[0]
    products = get_available_products(mc.market_products, start)
    orderbook = strategy.calculate_bids(
        storage_unit, market_config=mc, product_tuples=products
    )
    assert orderbook
    exclusive_ids = {o["exclusive_id"] for o in orderbook}
    assert exclusive_ids


def test_dmas_day(storage_day):
    strategy = DmasStorageStrategy()
    hour_count = len(storage_day.index) // 2
    assert hour_count == 24

    mc = MarketConfig(
        "Test",
        rr.rrule(rr.HOURLY),
        timedelta(hours=1),
        "not needed",
        [MarketProduct(timedelta(hours=1), hour_count, timedelta(hours=0))],
        additional_fields=["exclusive_id"],
    )
    start = storage_day.index[0]
    products = get_available_products(mc.market_products, start)
    orderbook = strategy.calculate_bids(
        storage_day, market_config=mc, product_tuples=products
    )
    assert orderbook
    exclusive_ids = {o["exclusive_id"] for o in orderbook}
    assert exclusive_ids