from typing import List
from pydantic import Field
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from hummingbot.strategy_v2.executors.order_executor.data_types import ExecutionStrategy, OrderExecutorConfig
from hummingbot.strategy_v2.controllers.volume_pumper_controller_base import VolumePumperControllerBase
from hummingbot.strategy_v2.controllers.volume_pumper_controller_base import VolumePumperConfigBase


class VolumePumperConfig(VolumePumperConfigBase):
    controller_name: str = "volume_pumper"
    candles_config: List[CandlesConfig] = Field(default=[])


class VolumePumperController(VolumePumperControllerBase):
    def __init__(self, config: VolumePumperConfig, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        self.config = config

    def get_executor_config(self, order: OrderCandidate):
        return OrderExecutorConfig(
            timestamp=self.market_data_provider.time(),
            connector_name=self.exchange,
            trading_pair=self.trading_pair,
            price=order.price,
            amount=order.amount,
            # triple_barrier_config=self.config.triple_barrier_config,
            side=order.order_side,
            execution_strategy=ExecutionStrategy.LIMIT,
        )
