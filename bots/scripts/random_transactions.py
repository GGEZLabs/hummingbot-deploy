import asyncio
import os
import random
from typing import Dict, List

import requests
from hummingbot.client.config.config_data_types import BaseClientModel, ClientFieldData
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.api_throttler.data_types import RateLimit
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from pydantic import Field, validator


class RandomTransactionConfig(BaseClientModel):
    script_file_name: str = Field(default_factory=lambda: os.path.basename(__file__))
    send_msg_url: str = Field(
        "",
        client_data=ClientFieldData(prompt_on_new=True, prompt=lambda mi: "Send message endpoint"),
    )
    ggezchain_rest_url: str = Field(
        "https://drest.ggez.one/cosmos/bank/v1beta1/spendable_balances",
        client_data=ClientFieldData(prompt_on_new=True, prompt=lambda mi: "Get balance endpoint"),
    )
    mnemonic_keys_with_addresses: List[Dict[str, str]] = Field(
        default=[],
        client_data=ClientFieldData(
            prompt_on_new=True,
            prompt=lambda mi: (
                "Enter the mnemonic keys with addresses in the format: " "'mnemonic1:address1,mnemonic2:address2,...'"
            ),
        ),
    )
    min_tx_amount: int = Field(
        1_000_000,
        client_data=ClientFieldData(prompt_on_new=True, prompt=lambda mi: "Minimum transaction amount (uggez1)"),
    )
    max_tx_amount: int = Field(
        3_000_000,
        client_data=ClientFieldData(prompt_on_new=True, prompt=lambda mi: "Maximum transaction amount (uggez1)"),
    )
    min_delay: int = Field(
        60,
        client_data=ClientFieldData(prompt_on_new=True, prompt=lambda mi: "Minimum delay in seconds"),
    )
    max_delay: int = Field(
        900,
        client_data=ClientFieldData(prompt_on_new=True, prompt=lambda mi: "Maximum delay in seconds"),
    )

    @validator("mnemonic_keys_with_addresses", pre=True, allow_reuse=True, always=True)
    def validate_mnemonic_keys(cls, v):
        if isinstance(v, str):
            mnemonic_list = v.split(",")
            mnemonic_objects = []
            for item in mnemonic_list:
                try:
                    mnemonic, address = item.split(":")
                    mnemonic_objects.append({"key": mnemonic.strip(), "address": address.strip()})
                except ValueError:
                    raise ValueError(
                        "Invalid format. Please provide input in the format: " "'mnemonic1:address1,mnemonic2:address2,...'"
                    )
            return mnemonic_objects
        return v


class RandomTransaction(ScriptStrategyBase):
    @classmethod
    def init_markets(self, config: RandomTransactionConfig):
        self.markets = {}

    def __init__(self, connectors: Dict[str, ConnectorBase], config: RandomTransactionConfig):
        super().__init__(connectors)
        self.config = config
        self._task = None

    rate_limits = [
        RateLimit(limit_id="Limits", limit=6000, time_interval=100),
    ]

    def on_tick(self):
        if self._task is None or self._task.done():
            self._task = safe_ensure_future(self.schedule_random_transactions())

    # send token using ggez api
    async def send_tokens_via_api(self, mnemonic, address_from, address_to, amount):
        payload = {
            "mnemonic_phrase": mnemonic,
            "address_from": address_from,
            "address_to": address_to,
            "amount": [{"amount": str(amount), "denom": "uggez1"}],
        }

        try:
            factory = WebAssistantsFactory(self.create_throttler())
            rest_assistant = await factory.get_rest_assistant()
            data = await rest_assistant.execute_request(
                url=self.config.send_msg_url,
                data=payload,
                throttler_limit_id="Limits",
                method=RESTMethod.POST,
            )
            return data
        except requests.exceptions.RequestException as e:
            self.logger().info(f"Error sending transaction: {e}")
            return None

    # send random tokens from random sender to random recipient
    async def execute_random_transactions(self):
        accounts = [{"key": entry["key"], "address": entry["address"]} for entry in self.config.mnemonic_keys_with_addresses]
        # check if there 2 addresses at least
        if len(accounts) < 2:
            self.logger().error("Insufficient accounts to perform a transaction.")
            return

        sender = random.choice(accounts)
        sender_key = sender["key"]
        sender_address = sender["address"]

        recipient = random.choice([acc for acc in accounts if acc["address"] != sender_address])
        recipient_address = recipient["address"]

        # Random amount in uggez1
        amount = random.randint(self.config.min_tx_amount, self.config.max_tx_amount)
        if amount % 1_000_000 != 0:
            amount = round(amount / 1_000_000) * 1_000_000
        try:
            balance = await self.get_account_balance(sender_address)
            uggez1_balance = next(
                (int(bal["amount"]) for bal in balance["balances"] if bal["denom"] == "uggez1"),
                0,
            )

            # check if sender_address has sufficient balance
            if uggez1_balance < (amount + 125_000):
                self.logger().info(
                    f"Insufficient balance for {sender_address}: {uggez1_balance} uggez1 (needed: {amount + 125_000})"
                )
                return

            self.logger().info(f"Sending {amount} uggez1 from {sender_address} to {recipient_address}")

            await self.send_tokens_via_api(sender_key, sender_address, recipient_address, amount)

        except Exception as e:
            self.logger().error(f"Error while processing transaction for {sender_address}: {e}")

    def create_throttler(self) -> AsyncThrottler:
        return AsyncThrottler(self.rate_limits)

    async def get_account_balance(self, sender_address):
        try:
            factory = WebAssistantsFactory(self.create_throttler())
            rest_assistant = await factory.get_rest_assistant()
            data = await rest_assistant.execute_request(
                url=f"{self.config.ggezchain_rest_url}/{sender_address}",
                throttler_limit_id="Limits",
                method=RESTMethod.GET,
            )
            return data
        except requests.exceptions.RequestException as e:
            self.logger().info(f"Error while getting account balance: {e}")
            return None

    async def schedule_random_transactions(self):
        delay_seconds = random.randint(self.config.min_delay, self.config.max_delay)
        self.logger().info(f"Scheduling next transaction in {delay_seconds} second(s).")
        await asyncio.sleep(delay_seconds)
        await self.execute_random_transactions()
