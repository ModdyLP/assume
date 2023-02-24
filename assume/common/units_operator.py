import asyncio
from assume.common.marketconfig import MarketConfig
from assume.units import BaseUnit
from assume.strategies import BaseStrategy

from mango import Role
from mango.messages.message import Performatives
from assume.common.orders import (
    Order,
    Orderbook,
    OpeningMessage,
    ClearingMessage,
)
import logging
logger = logging.getLogger(__name__)


class UnitsOperator(Role):
    def __init__(self,
                 available_markets: list[MarketConfig],
                 opt_portfolio: dict[bool, BaseStrategy]=None
                 ):
        super().__init__()
        
        self.available_markets = available_markets
        self.registered_markets: dict[str, MarketConfig] = {}

        if opt_portfolio is None:
            self.use_portfolio_opt = False
            self.portfolio_strategy = None
        else:
            self.use_portfolio_opt = opt_portfolio[0]
            self.portfolio_strategy = opt_portfolio[1]
        
        self.valid_orders = []
        self.units = {}
                
    def setup(self):
        self.id = self.context.aid
        self.context.subscribe_message(
            self,
            self.handle_opening,
            lambda content, meta: content.get("context") == "opening",
        )

        self.context.subscribe_message(
            self,
            self.handle_market_feedback,
            lambda content, meta: content.get("context") == "clearing",
        )

        for market in self.available_markets:
            if self.participate(market):
                self.register_market(market)
                self.registered_markets[market.name] = market

    
    def participate(self, market):
        # always participate at all markets
        return True


    def register_market(self, market):
        self.context.schedule_timestamp_task(
            self.context.send_acl_message(
                {"context": "registration", "market": market.name},
                market.addr,
                receiver_id=market.aid,
                acl_metadata={
                    "sender_addr": self.context.addr,
                    "sender_id": self.context.aid,
                },
            ),
            1,  # register after time was updated for the first time
        )

    def handle_opening(self, opening: OpeningMessage, meta: dict[str, str]):
        logger.debug(f'Received opening from: {opening["market"]} {opening["start"]}.')
        logger.debug(f'can bid until: {opening["stop"]}')

        self.context.schedule_instant_task(coroutine=self.submit_bids(opening))

    def send_dispatch_plan(self):
        valid_orders = self.valid_orders
        # todo group by unit_id
        for unit in self.units:
            unit.dispatch(valid_orders)
    
    def handle_market_feedback(self, content: ClearingMessage, meta: dict[str, str]):
        logger.debug(f"got market result: {content}")
        orderbook: Orderbook = content["orderbook"]
        for bid in orderbook:
            self.valid_orders.append(bid)
        
        self.send_dispatch_plan()

    async def submit_bids(self, opening):
        """
            send the formulated order book to the market. OPtion for further
            portfolio processing

            Return:
        """

        products = opening["products"]
        market = self.registered_markets[opening["market"]]
        logger.debug(f"setting bids for {market.name}")
        orderbook = self.formulate_bid(market, products)
        acl_metadata = {
            "performative": Performatives.inform,
            "sender_id": self.context.aid,
            "sender_addr": self.context.addr,
            "conversation_id": "conversation01",
        }
        await self.context.send_acl_message(
            content={
                "market": market.name,
                "orderbook": orderbook,
            },
            receiver_addr=market.addr,
            receiver_id=market.aid,
            acl_metadata=acl_metadata,
        )

    async def formulate_bids(self, market: MarketConfig, products):
        # sourcery skip: merge-dict-assign

        """
            Takes information from all units that the unit operator manages and
            formulates the bid to the market from that according to the bidding strategy.

            Return: OrderBook that is submitted as a bid to the market
        """

        orderbook: Orderbook = []
        for product in products:
            if self.use_portfolio_opt==False:
                for unit in self.units:
                    order: Order = {}
                    order["start_time"] = product[0]
                    order["end_time"] = product[1]
                    order["agent_id"] = (self.context.addr, self.context.aid)
                    #get operational window for each unit
                    operational_window= unit.calculate_operational_window()
                    #get used bidding strategy for the unit
                    unit_strategy = unit['bidding_strategy'] 
                    #take price from bidding strategy
                    order["volume"], order["price"] = unit_strategy.calculate_bids(market,  operational_window)

                    orderbook.append(order)

            else:
                raise NotImplementedError

        return orderbook

    def add_unit(self, id:str, unit_class: BaseUnit, unit_params: dict, bidding_strategy: BaseStrategy=None):
        """
        Create a unit.
        """
        self.units[id] = unit_class(id, **unit_params)
        self.units[id].bidding_strategy = bidding_strategy

        if bidding_strategy is None and self.use_portfolio_opt == False:
            raise ValueError("No bidding strategy defined for unit while not using portfolio optimization.")

    #Needed data in the future 
    """""
    def get_world_data(self, input_data):
        self.temperature = input_data.temperature
        self.wind_speed = input_data.wind_speed

    def location(self, coordinates: tuple(float, float)= (0,0), NUTS_0: str = None):
        self.x: int = 0
        self.y: int = 0
        NUTS_0: str = 0

    def get_temperature(self, location):
        if isinstance(location, tuple):
            # get lat lon table
            pass
        elif "NUTS" in location:
            # get nuts table
            pass
            
    def reset(self):
    
        #Reset the unit to its initial state.

    """