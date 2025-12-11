import asyncio
import os
from decimal import Decimal
from typing import Dict, List

from hummingbot.client.config.config_data_types import BaseClientModel
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.data_type.common import PriceType
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from pydantic import Field, field_validator


class VolumeMonitorConfig(BaseClientModel):
    script_file_name: str = os.path.basename(__file__)
    trading_pair: str = Field(
        "GGEZ1-USDT", json_schema_extra={"prompt": lambda mi: "trading pair to monitor", "prompt_on_new": True}
    )
    exchanges: List[str] = Field(
        ["p2b", "coinstore", "uzx"],
        json_schema_extra={
            "prompt": lambda mi: "exchanges to monitor separated by commas (e.g. p2b,coinstore,uzx)",
            "prompt_on_new": True,
        },
    )
    refresh_time: int = Field(300, json_schema_extra={"prompt": lambda mi: "refresh time in seconds", "prompt_on_new": True})
    volume_threshold: Decimal = Field(
        50000, json_schema_extra={"prompt": lambda mi: "volume threshold in (quote)", "prompt_on_new": True}
    )

    @field_validator("exchanges", mode="before")
    @classmethod
    def validate_sets(cls, v):
        if isinstance(v, str):
            return list(v.split(","))
        return v


class VolumeMonitor(ScriptStrategyBase):
    """
    This bot monitors the trading volume of a specified pair across multiple exchanges.
    At regular `refresh_time` intervals, it checks the current volume against a `volume_threshold`.
    If the volume is below the threshold, a notification is sent to the user via Telegram.
    If the volume is above the threshold, a log message is printed.
    The bot is designed to be API-efficient, remaining idle for most of the time between checks.

    the config :
    exchange: List[str] = ["p2b", "coinstore" , "uzx"]
    trading_pair: str = Field("ETH-USDT")
    refresh_time: int = Field(15)
    volume_threshold: Decimal = Field(1)

    """

    price_source = PriceType.MidPrice

    @classmethod
    def init_markets(cls, config: VolumeMonitorConfig):
        cls.markets = {exchange: {config.trading_pair} for exchange in config.exchanges}
        cls.price_source = PriceType.MidPrice

    def __init__(self, connectors: Dict[str, ConnectorBase], config: VolumeMonitorConfig):
        super().__init__(connectors)
        self.config = config
        self._task = None
        self.last_volumes = {}

    def on_tick(self):
        # check the volume of the trading pair on each exchange
        # if the volume is above the threshold, print a message
        # else notify the user ( by telegram ) that the volume is below the threshold
        if self._task is None or self._task.done():
            self._task = safe_ensure_future(self.check_volume())

    async def check_volume(self):
        for exchange in self.config.exchanges:
            volume = await self.connectors[exchange].get_volume(self.config.trading_pair)
            self.last_volumes[exchange] = volume
            if volume < self.config.volume_threshold:
                self.logger().notify(f"\n⚠️Warning⚠️:\nVolume is below the threshold ({volume}) on {exchange}")

            await asyncio.sleep(self.config.refresh_time)

    def format_status(self) -> str:
        text = ""
        current_volumes = "Current Volumes: "
        current_prices = "Current Prices: "
        for exchange in self.config.exchanges:
            if exchange not in self.last_volumes:
                continue
            current_volumes += f"\n{exchange}: {self.last_volumes[exchange]} {self.config.trading_pair.split('-')[1]}"
            current_prices += f"\n{exchange}: {self.connectors[exchange].get_mid_price(self.config.trading_pair)} {
                                            self.config.trading_pair.split('-')[0]}"

        return text + f"\n\n{current_volumes}\n\n{current_prices}"
