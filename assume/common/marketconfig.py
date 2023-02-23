from mango import Agent, Role
from datetime import datetime, timedelta
from dateutil import rrule as rr
from dateutil.relativedelta import relativedelta as rd
import logging
from dataclasses import dataclass, field
from typing import Callable, TypedDict
from numpy.typing import ArrayLike

logger = logging.getLogger(__name__)


class Order(TypedDict):
    start_time: datetime | float
    end_time: datetime | float
    volume: float
    price: float
    only_hours: tuple[int, int]
    agent_id: str


Orderbook = list[Order]
MarketOrderbook = dict[str, Orderbook]

contract_type = Callable[[Agent, Agent], None]
market_contract_type = Callable[[Agent, Agent, ArrayLike], None]
eligible_lambda = Callable[[Agent], bool]

# describes the configuration of an actual product traded at the market
@dataclass
class RealMarketProduct:
    issued_time: datetime
    delivery_start_time: datetime
    delivery_end_time: datetime
    price: float
    volume: float


# describes the configuration of a market product which is available at a market
@dataclass
class MarketProduct:
    duration: rd  # quarter-hourly, half-hourly, hourly, 4hourly, daily, weekly, monthly, quarter-yearly, yearly
    count: int  # how many future durations can be traded, must be >= 1
    # count can also be given as a rrule with until
    first_delivery_after_start: rd = (
        rd()
    )  # when does the first delivery begin, in relation to market start
    # this should be a multiple of duration
    only_hours: tuple[
        int, int
    ] | None = None  # e.g. (8,20) - for peak trade, (20, 8) for off-peak, none for base
    eligible_lambda_function: eligible_lambda | None = None


market_mechanism = Callable[[Role, list[MarketProduct]], tuple[Orderbook, dict]]


@dataclass
class MarketConfig:
    name: str
    addr = None
    aid = None
    # filled by market agent

    # continuous markets are clearing just very fast and keep unmatched orders between clearings
    opening_hours: rr.rrule  # dtstart ist start/introduction of market
    opening_duration: timedelta
    market_mechanism: market_mechanism  # market_mechanism determines wether old offers are deleted (continuous) or not (auction) after clearing
    # if continuous: one of [pay_as_bid, pay_as_ask] else: pay_as_clear

    maximum_bid: float = 9999
    minimum_bid: float = -500
    maximum_gradient: float = None  # very specific - should be in market clearing
    maximum_volume: int = 500
    additional_fields: list[str] = field(default_factory=list)
    market_products: list[MarketProduct] = field(default_factory=list)
    amount_unit: str = "MW"
    amount_tick: float = 0.1  # steps in which the amount can be increased
    price_unit: str = "€"
    price_tick: float = 0.1  # steps in which the price can be increased
    eligible_obligations_lambda: eligible_lambda = lambda x: True
    # lambda: agent.payed_fee
    # obligation should be time-based
    # only allowed to bid regelenergie if regelleistung was accepted in the same hour for this agent by the market


# Class for a Smart Contract which can contain something like:
# - Contract for Differences (CfD) -> based on market result
# - Market Subvention -> based on market result
# - Power Purchase Agreements (PPA) -> A buys everything B generates for price x
# - Swing Contract ->


def ppa(buyer: Agent, seller: Agent):
    set_price = 26  # ct/kWh
    buyer.generation += seller.generation
    seller.revenue += seller.generation * set_price
    buyer.revenue -= seller.generation * set_price
    seller.generation = 0


def swingcontract(buyer: Agent, seller: Agent):
    set_price = 26  # ct/kWh
    outer_price = 45  # ct/kwh
    if minDCQ < buyer.demand and buyer.demand < maxDCQ:
        cost = buyer.demand * set_price
    else:
        cost = outer_price
    buyer.revenue -= buyer.demand * cost
    seller.revenue += buyer.demand * cost


def cfd(buyer: Agent, seller: Agent, market_index):
    set_price = 26  # ct/kWh
    cost = set_price - market_index
    seller.revenue += cost
    buyer.revenue -= cost


def eeg(buyer: Agent, seller: Agent, market_index):
    set_price = 26  # ct/kWh
    cost = set_price - market_index
    if cost > 0:
        seller.revenue += cost
        buyer.revenue -= cost


d = datetime.now()
today = datetime(d.year, d.month, d.day)

# relevant information
# https://www.next-kraftwerke.de/wissen/spotmarkt-epex-spot
# https://www.epexspot.com/sites/default/files/2023-01/22-10-25_TradingBrochure.pdf

# EPEX DayAhead-Auction:
# https://www.epexspot.com/en/tradingproducts#day-ahead-trading
# 45 days ahead (5 weeks)
# https://www.epexspot.com/sites/default/files/download_center_files/EPEX%20SPOT%20Market%20Rules_0_0.zip

epex_dayahead_auction_config = MarketConfig(
    "epex_dayahead_auction",
    additional_fields=["link", "offer_id"],
    market_products=[MarketProduct(rd(hours=+1), 24 * 45, rd(days=2, hour=0))],
    # continuous=False, # orders persist between clearings - shorter intervals
    opening_hours=rr.rrule(
        rr.DAILY, byhour=12, dtstart=datetime(2005, 6, 1), until=datetime(2030, 12, 31)
    ),
    opening_duration=timedelta(days=1),
    maximum_gradient=0.1,  # can only change 10% between hours - should be more generic
    amount_unit="MWh",
    amount_tick=0.1,
    price_unit="€/MW",
    market_mechanism="pay_as_clear",
)
# uniform pricing/merit order

# EPEX Intraday-Auction:
# https://www.epexspot.com/en/tradingproducts#intraday-trading
# closes/opens at 15:00 every day
epex_intraday_auction_config = MarketConfig(
    "epex_intraday_auction",
    market_products=[
        MarketProduct(
            duration=rd(minutes=+15),
            count=96,
            first_delivery_after_start=rd(days=2, hour=0),
        )
    ],
    # continuous=False,
    opening_hours=rr.rrule(
        rr.DAILY,
        byhour=15,
        dtstart=datetime(2011, 12, 15),
        until=datetime(2023, 12, 31),
    ),
    opening_duration=timedelta(days=1),
    amount_unit="MWh",
    amount_tick=0.1,
    price_unit="€/MWh",
    price_tick=0.01,
    maximum_bid=4000,
    minimum_bid=-3000,
    market_mechanism="pay_as_clear",
)
# uniform pricing/merit order

# EPEX IntraDay-Trading:
# https://www.epexspot.com/en/tradingproducts#intraday-trading
# Price list 2019: https://www.coursehero.com/file/43528280/Price-listpdf/
# 25000€ Entry fee
# DAM + IDM 10000€/a
# IDM only 5000€/a
# 15m IDM auction 5000€/a
# https://www.epexspot.com/en/downloads#rules-fees-processes

# Trading should start at 15:00
def dynamic_end(current_time: datetime):
    if current_time.hour < 15:
        # if the new auction day did not start- only the rest of today can be traded
        return rd(days=+1, hour=0)
    else:
        # after 15:00 the next day can be traded too
        return rd(days=+2, hour=0)


# TODO: area specific dependencies
# eligible_lambda for marketproducts (also see RAM)
# 60 minutes before for xbid
# 30 minutes before in DE
# 5 minutes before in same TSO area
CLEARING_FREQ_MINUTES = 5
epex_intraday_trading_config = MarketConfig(
    name="epex_intraday_trading",
    opening_hours=rr.rrule(
        rr.MINUTELY,
        interval=CLEARING_FREQ_MINUTES,
        dtstart=datetime(2013, 11, 1),
        until=datetime(2023, 12, 31),
    ),
    opening_duration=timedelta(minutes=CLEARING_FREQ_MINUTES),
    market_products=[
        MarketProduct(rd(minutes=+15), dynamic_end, rd(minutes=+5)),
        MarketProduct(rd(minutes=+30), dynamic_end, rd(minutes=30)),
        MarketProduct(rd(hours=+1), dynamic_end, rd(minutes=30)),
    ],
    eligible_obligations_lambda=lambda agent, market: agent.aid in market.participants
    and agent.payed > 10000,  # per year + 25k once
    market_mechanism="continuous_clearing",  # only one orderbook is retained per agent
    amount_unit="MWh",
    amount_tick=0.1,
    price_unit="€/MWh",
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
)
# pay as bid
# publishes market results to TSO every 15 minutes
# matching findet nur in eigener Regelzone für die letzen 15 Minuten statt - sonst mindestens 30 Minuten vorher

workdays = (rr.MO, rr.TU, rr.WE, rr.TH, rr.FR)

# TerminHandel:
# https://www.eex.com/en/markets/power/power-futures
# Price List: https://www.eex.com/fileadmin/EEX/Downloads/Trading/Price_Lists/20230123_Price_List_EEX_AG_0107a_E_FINAL.pdf
# Transaktionsentgelt: 0,0075 €/MWh
# 22000€ Teilnahme pro Jahr
# open from 8:00 to 18:00 on workdays
# https://www.eex.com/en/markets/power/power-futures
# continuous clearing - approximated through 5 minute intervals
# trading structure:
# https://www.eex.com/en/markets/trading-ressources/rules-and-regulations
CLEARING_FREQ_MINUTES = 5
first_after_start = rd(days=2, hour=0)
eex_future_trading_config = MarketConfig(
    name="eex_future_trading",
    additional_fields=["link", "offer_id"],
    opening_hours=rr.rrule(
        rr.MINUTELY,
        interval=CLEARING_FREQ_MINUTES,
        byhour=range(8, 18),
        byweekday=workdays,
        dtstart=datetime(2002, 1, 1),
        until=datetime(2023, 12, 31),
    ),
    opening_duration=timedelta(minutes=CLEARING_FREQ_MINUTES),
    market_products=[
        MarketProduct(rd(days=+1, hour=0), 7, first_after_start),
        MarketProduct(rd(weeks=+1, weekday=0, hour=0), 4, first_after_start),
        MarketProduct(rd(months=+1, day=1, hour=0), 9, first_after_start),
        MarketProduct(
            rr.rrule(rr.MONTHLY, bymonth=(1, 4, 7, 10), bymonthday=1, byhour=0),
            11,
            first_after_start,
        ),
        MarketProduct(rd(years=+1, yearday=1, hour=0), 10, first_after_start),
    ],
    maximum_bid=9999,
    minimum_bid=-9999,
    amount_unit="MW",  # offer volume is in MW for whole product duration
    amount_tick=0.1,
    price_unit="€/MWh",  # cost is given in €/MWh - total product cost results in price*amount/(duration in hours)
    price_tick=0.01,
    eligible_obligations_lambda=lambda agent, market: agent.aid in market.participants
    and agent.payed > 22000,  # per year
    market_mechanism="pay_as_bid",
)

# AfterMarket:
# https://www.epexspot.com/en/tradingproducts#after-market-trading
NOW = datetime.now()

# Trading end should be 12:30 day after delivery (D+1) - dynamic repetition makes it possible
def dynamic_repetition(current_time):
    if current_time.hour < 13:
        return +(24 + current_time.hour)
    else:
        return +(current_time.hour)


epex_aftermarket_trading_config = MarketConfig(
    "epex_aftermarket",
    additional_fields=["link", "offer_id"],
    market_products=[
        # negative duration, to go back in time
        MarketProduct(rd(hours=-1), dynamic_repetition, timedelta()),
    ],
    opening_hours=rr.rrule(
        rr.MINUTELY,
        interval=CLEARING_FREQ_MINUTES,
        byhour=range(8, 18),
        byweekday=workdays,
        dtstart=datetime(2023, 1, 1),
        until=datetime(2023, 12, 31),
    ),
    opening_duration=timedelta(minutes=CLEARING_FREQ_MINUTES),
    amount_unit="MWh",
    amount_tick=0.1,
    price_unit="€/MWh",
    price_tick=0.01,
    # continuous=True,
    maximum_bid=9999,
    minimum_bid=-9999,
    market_mechanism="pay_as_bid",
)

# EPEX Emissionsmarkt Spot:
# EU Allowance (EUA)
# https://www.eex.com/de/maerkte/umweltprodukte/eu-ets-auktionen
# https://www.eex.com/de/maerkte/umweltprodukte/eu-ets-spot-futures-options
# https://www.eex.com/fileadmin/EEX/Markets/Environmental_markets/Emissions_Spot__Futures___Options/20200619-EUA_specifications_v2.pdf

"""
epex_emission_trading_config = MarketConfig(
    today,
    market_products=[
        MarketProduct('yearly', 10),
    ],
    #continuous=True,
    amount_unit='t CO2',
    amount_tick=1,
    price_unit='€/t',
    price_tick=5,
)

p2p_trading_config = MarketConfig(
    today,
    additional_fields=['sender_id', 'receiver_id'],
    market_products=[
        MarketProduct('quarter-hourly', 96),
        MarketProduct('half-hourly', 48),
        MarketProduct('hourly', 24),
    ],
    #continuous=True,
    amount_unit='kWh',
    price_unit='€/kWh',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
)

# eligible_lambda is a lambda to check if an agent is eligible to receive a policy (must have solar...)
# TODO define how contracts look like - maybe just a string?
policy_trading_config = MarketConfig(
    today,
    additional_fields=['sender_id', 'eligible_lambda', 'contract'], # agent_id, eligible_lambda, MarketContract/Contracttype
    market_products=[
        MarketProduct('monthly', 12),
        MarketProduct('quarter-yearly', 1),
        MarketProduct('yearly', 1),
    ],
    #continuous=True,
    amount_unit='MW',
    price_unit='€/MWh',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
    # laufzeit vs abrechnungszeitraum
)

# Control Reserve market
# regelleistung kann 7 Tage lang geboten werden (überschneidende Gebots-Zeiträume)?
# FCR
market_start = today - timedelta(days=7) + timedelta(hours=10)
control_reserve_trading_config = MarketConfig(
    today,
    additional_fields=['eligible_lambda'], # eligible_lambda
    market_products=[
        MarketProduct(rd(hours=+4), 6*7, rd(days=+1)),
    ],
    opening_hours=rr.rrule(rr.DAILY, market_start),
    opening_duration=timedelta(days=7),
    amount_unit='MW',
    amount_tick=0.1,
    price_unit='€/MW',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
) # pay-as-bid/merit-order one sided

# RAM Regelarbeitsmarkt - Control Reserve
market_start = today - timedelta(days=2) + timedelta(hours=12)
control_work_trading_config = MarketConfig(
    today,
    additional_fields=['eligible_lambda'],
    market_products=[
        MarketProduct('quarter-hourly', 96),
    ],
    #continuous=False,
    opening_hours=rr.rrule(rr.DAILY, market_start),
    opening_duration=timedelta(days=1),
    amount_unit='MW',
    amount_tick=0.1,
    price_unit='€/MW',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
    # obligation = innerhalb von 1 minute reagieren kann
) # pay-as-bid/merit-order

# MISO Nodal market
# https://help.misoenergy.org/knowledgebase/article/KA-01024/en-us
market_start = today - timedelta(days=14) + timedelta(hours=10, minutes=30)
# 05.2010
miso_day_ahead_config = MarketConfig(
    today,
    additional_fields=['node_id'],
    market_products=[
        MarketProduct('hourly', 24),
    ],
    #continuous=False,
    opening_hours=rr.rrule(rr.DAILY, market_start),
    opening_duration=timedelta(days=1),
    amount_unit='MW',
    price_unit='$/MW',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
    eligible_lambda=lambda agent: agent.location
) # pay-as-bid/merit-order

# ISO gibt spezifisches Marktergebnis welches nicht teil des Angebots war

# Contour Map
# https://www.misoenergy.org/markets-and-operations/real-time--market-data/markets-displays/
# Realtime Data API
# https://www.misoenergy.org/markets-and-operations/RTDataAPIs/
# SCED
# https://help.misoenergy.org/knowledgebase/article/KA-01112/en-us
# Market Closure Table (unclear)
# https://help.misoenergy.org/knowledgebase/article/KA-01163/en-us
# Metrics:
# https://cdn.misoenergy.org/202211%20Markets%20and%20Operations%20Report627372.pdf (p. 60-63)
# Start 12.2009
miso_real_time_config = MarketConfig(
    today,
    additional_fields=['node_id'],
    market_products=[
        MarketProduct('5minutes', 12),
        # unclear how many slots can be traded?
        # at least the current hour
    ],
    #continuous=False,
    opening_hours=rr.rrule(rr.MINUTELY, interval=5, dtstart=today-timedelta(hours=1)),
    opening_duration=timedelta(hours=1),
    amount_unit='MW',
    price_unit='$/MW',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
    eligible_lambda=lambda agent: agent.location in BW,
    clearing = "twoside_clearing"
) # pay-as-bid/merit-order


result_bids = clearing(self, input_bids)
"""

# asymmetrical auction
# one sided acution

# GME market - italian
# which market products exist?
# 11.2007


# PJM: https://pjm.com/markets-and-operations/energy/real-time/historical-bid-data/unit-bid.aspx
# DataMiner: https://dataminer2.pjm.com/feed/da_hrl_lmps/definition
# ContourMap: https://pjm.com/markets-and-operations/interregional-map.aspx

# TODO: ISO NE, ERCOT, CAISO


## Agenten müssen ihren Verpflichtungen nachkommen
## TODO: geographische Voraussetzungen - wer darf was - Marktbeitrittsbedingungen


# LMP Markt:
# https://www.e-education.psu.edu/eme801/node/498
# Alle Contraints und marginal Costs werden gesammelt
# Markt dispatched kosten an Demand nach Stability constrained Merit-Order
# Teilnehmer werden nur mit Marginal Costs bezahlt
# differenz ist congestion revenue -> behält TSO ein?

# All operating facilities in the U.S. devote the first portion of their revenues to the maintenance and operations of the priced lanes.
# The traffic monitoring, tolling, enforcement, incident management, administration, and routine maintenance costs can be significant,
# https://www.cmap.illinois.gov/updates/all/-/asset_publisher/UIMfSLnFfMB6/content/examples-of-how-congestion-pricing-revenues-are-used-elsewhere-in-the-u-s-


# Virtual profitability Index:
# sum of all profits (transactions settled above price) / Total traded MWh


# Which roles do you need for the market


### Auswertung Index - Benchmark
# https://www.eex.com/fileadmin/EEX/Downloads/Trading/Specifications/Indeces/DE/20200131-indexbeschreibung-v009b-d-final-track-changes-data.pdf
