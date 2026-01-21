"""
Volume Pumper Strategy Entry Point.

This module provides the entry point for the Volume Pumper trading strategy.
It uses the refactored SOLID architecture from hummingbot.strategy_v2.volume_pumper.
"""

from typing import List

from pydantic import Field

from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from hummingbot.strategy_v2.utils.volume_pumper_config import VolumePumperConfigBase
from hummingbot.strategy_v2.volume_pumper.controller import (
    VolumePumperController as VolumePumperControllerBase,
    create_volume_pumper_controller,
)


class VolumePumperConfig(VolumePumperConfigBase):
    """Configuration for the Volume Pumper strategy."""

    controller_name: str = "volume_pumper"
    candles_config: List[CandlesConfig] = Field(default=[])


class VolumePumperController(VolumePumperControllerBase):
    """
    Volume Pumper Controller entry point.

    This class serves as the entry point for Hummingbot's controller loading system.
    It uses the new SOLID architecture by creating all dependencies via the factory
    function and passing them to the parent class.
    """

    def __new__(
        cls,
        config: VolumePumperConfig,
        market_data_provider,
        actions_queue=None,
        *args,
        **kwargs
    ):
        """
        Create a new VolumePumperController instance using the factory function.

        This approach allows us to use dependency injection while maintaining
        compatibility with Hummingbot's controller loading system.

        Args:
            config: Strategy configuration
            market_data_provider: Market data provider from executor orchestrator
            actions_queue: Actions queue for sending executor actions
        """
        return create_volume_pumper_controller(
            config=config,
            market_data_provider=market_data_provider,
            actions_queue=actions_queue,
            *args,
            **kwargs,
        )
