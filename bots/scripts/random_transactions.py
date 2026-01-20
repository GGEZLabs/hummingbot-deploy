import os
import random
import time
from typing import Dict, List

from pydantic import Field, SecretStr, field_validator

from hummingbot.client.config.config_data_types import BaseClientModel
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.strategy_v2.utils.cosmos_grpc_client import CosmosGrpcClient


class RandomTransactionConfig(BaseClientModel):
    script_file_name: str = Field(default_factory=lambda: os.path.basename(__file__))
    chain_id: str = Field(
        default="ggezchain",
        json_schema_extra={
            "prompt": "Enter chain ID",
            "prompt_on_new": True,
        },
    )
    grpc_url: str = Field(
        default="172.21.10.116:9090",
        json_schema_extra={
            "prompt": "Enter GRPC endpoint",
            "prompt_on_new": True,
        },
    )
    denom: str = Field(
        default="uggez1",
        json_schema_extra={
            "prompt": "Enter token denom",
            "prompt_on_new": True,
        },
    )
    mnemonic_keys_with_addresses: SecretStr = Field(
        default=...,
        json_schema_extra={
            "prompt": "Enter mnemonic keys with addresses (format: 'mnemonic1:address1,mnemonic2:address2,...')",
            "prompt_on_new": True,
            "is_secure": True,
        },
    )
    min_tx_amount: int = Field(
        default=1_000_000,
        json_schema_extra={
            "prompt": "Enter minimum transaction amount (uggez1)",
            "prompt_on_new": True,
        },
    )
    max_tx_amount: int = Field(
        default=3_000_000,
        json_schema_extra={
            "prompt": "Enter maximum transaction amount (uggez1)",
            "prompt_on_new": True,
        },
    )
    min_delay: int = Field(
        default=60,
        json_schema_extra={
            "prompt": "Enter minimum delay in seconds",
            "prompt_on_new": True,
        },
    )
    max_delay: int = Field(
        default=900,
        json_schema_extra={
            "prompt": "Enter maximum delay in seconds",
            "prompt_on_new": True,
        },
    )

    @field_validator("mnemonic_keys_with_addresses", mode="before")
    @classmethod
    def convert_to_secret_str(cls, v):
        """Convert string input to SecretStr."""
        if isinstance(v, str):
            return SecretStr(v)
        return v


class RandomTransaction(ScriptStrategyBase):
    @classmethod
    def init_markets(self, config: RandomTransactionConfig):
        self.markets = {}

    def __init__(
        self, connectors: Dict[str, ConnectorBase], config: RandomTransactionConfig
    ):
        super().__init__(connectors)
        self.config = config
        self.cosmos_grpc_client = CosmosGrpcClient(
            grpc_url=self.config.grpc_url,
            chain_id=self.config.chain_id,
        )
        self.last_tx_timestamp = 0
        self.current_random_delay = 0
        # Parse the decrypted mnemonic string into accounts list
        self.accounts = self._parse_mnemonics(
            self.config.mnemonic_keys_with_addresses.get_secret_value()
        )
        if len(self.accounts) < 2:
            raise ValueError("At least two mnemonic keys with addresses are required.")
        self.cumulating_transactions = self.cumulating_transactions()

    def _parse_mnemonics(self, raw: str) -> List[Dict[str, str]]:
        """Parse mnemonic:address pairs from the decrypted string."""
        if not raw:
            return []
        accounts = []
        for item in raw.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                mnemonic, address = item.split(":")
                accounts.append({"key": mnemonic.strip(), "address": address.strip()})
            except ValueError:
                raise ValueError(
                    f"Invalid format for '{item}'. Use: 'mnemonic1:address1,mnemonic2:address2,...'"
                )
        return accounts

    @property
    def is_ready_to_do_tx(self):
        return (
            self.current_timestamp - self.last_tx_timestamp > self.current_random_delay
        )

    def on_tick(self):
        if self.is_ready_to_do_tx:
            self.last_tx_timestamp = self.current_timestamp
            self.current_random_delay = random.randint(
                self.config.min_delay, self.config.max_delay
            )
            self.execute_random_transactions()

    # send token using ggez grpc client
    def send_tokens(self, mnemonic, address_from, address_to, amount):
        try:
            data = self.cosmos_grpc_client.send_tokens(
                sender_mnemonic=mnemonic,
                from_address=address_from,
                to_address=address_to,
                amount=amount,
                denom=self.config.denom,
            )
            return data
        except Exception as e:
            self.logger().info(f"Error sending transaction: {e}")
            return None

    def get_account_balance(self, sender_address):
        try:
            data = self.cosmos_grpc_client.get_balance(
                sender_address, self.config.denom
            )
            return data
        except Exception as e:
            self.logger().info(f"Error while getting account balance: {e}")
            return None

    # send random tokens from random sender to random recipient
    def execute_random_transactions(self):
        # check if there 2 addresses at least
        if len(self.accounts) < 2:
            self.logger().error("Insufficient accounts to perform a transaction.")
            return

        sender = random.choice(self.accounts)
        sender_key = sender["key"]
        sender_address = sender["address"]

        recipient = random.choice(
            [acc for acc in self.accounts if acc["address"] != sender_address]
        )
        recipient_address = recipient["address"]

        # Random amount in uggez1
        amount = random.randint(self.config.min_tx_amount, self.config.max_tx_amount)
        if amount % 1_000_000 != 0:
            amount = round(amount / 1_000_000) * 1_000_000
        try:
            uggez1_balance = self.get_account_balance(sender_address)

            # check if sender_address has sufficient balance
            if uggez1_balance < (amount + 125_000):
                self.logger().info(
                    f"Insufficient balance for {sender_address}: {uggez1_balance} uggez1 (needed: {amount + 125_000})"
                )
                return

            self.logger().info(
                f"Sending {amount} uggez1 from {sender_address} to {recipient_address}"
            )
            # retry if failed
            for i in range(3):
                try:
                    tsx_hash = self.send_tokens(
                        sender_key, sender_address, recipient_address, amount
                    )
                    if tsx_hash:
                        self.logger().info(
                            f"Transaction sent successfully for {sender_address}: {tsx_hash}"
                        )
                        self.cumulating_transactions.add_transaction(
                            {
                                "from": sender_address,
                                "to": recipient_address,
                                "amount": amount,
                            }
                        )
                        break
                except Exception as e:
                    self.logger().error(
                        f"Error while sending transaction for {sender_address}: {e} {i + 1}/3 retrying after 5 seconds... "
                    )
                    time.sleep(5)

        except Exception as e:
            self.logger().error(
                f"Error while processing transaction for {sender_address}: {e}"
            )

    def format_status(self) -> str:
        denom = self.config.denom[1:]
        tsx_info = (
            f"\nStrategy Config :"
            f"\nTransaction Amount Range: {self.convert_from_micro_denom_to_denom(self.config.min_tx_amount)} - {self.convert_from_micro_denom_to_denom(self.config.max_tx_amount)} {denom}"
            f"\nDelay Order Time: {self.config.min_delay} seconds + Random Delay: 0 - {self.config.max_delay} seconds"
            f"\nNumber of Accounts: {len(self.accounts)}"
            "\n"
            "\nTotal Cumulating Transactions:"
            f"\nTotal Transactions: {self.cumulating_transactions.total_transactions}"
            f"\nTotal Amount: {self.convert_from_micro_denom_to_denom(self.cumulating_transactions.total_amount)} {denom}"
            f"\nAverage Amount: {self.convert_from_micro_denom_to_denom(self.cumulating_transactions.total_amount / self.cumulating_transactions.total_transactions)} {denom}"
            "\n"
            "\nCumulating Transactions by Account:"
        )

        for account in self.accounts:
            tsx_info += f"\nAccount: {account['address']}"
            cumulating_transactions = (
                self.cumulating_transactions.get_account_transactions(
                    account["address"]
                )
            )
            if cumulating_transactions["count"] == 0:
                tsx_info += "\nTotal Transactions: 0"
                tsx_info += f"\nTotal Amount: 0 {denom}"
                tsx_info += f"\nAverage Amount: 0 {denom}"
            else:
                tsx_info += f"\nTotal Transactions: {cumulating_transactions['count']}"
                tsx_info += f"\nTotal Amount: {self.convert_from_micro_denom_to_denom(cumulating_transactions['total'])} {denom}"
                tsx_info += f"\nAverage Amount: {self.convert_from_micro_denom_to_denom(cumulating_transactions['total'] / cumulating_transactions['count'])} {denom}"

        return tsx_info

    def convert_from_micro_denom_to_denom(self, amount: float):
        return round(amount / 1_000_000, 6)

    class cumulating_transactions:
        def __init__(self):
            # {"address": {"total": 0, "count": 0}}
            self.transactions_by_account = {}
            self.total_transactions = 0
            self.total_amount = 0

        def add_transaction(self, transaction):
            if transaction["from"] not in self.transactions_by_account:
                self.transactions_by_account[transaction["from"]] = {
                    "total": 0,
                    "count": 0,
                }
            self.transactions_by_account[transaction["from"]]["total"] += transaction[
                "amount"
            ]
            self.transactions_by_account[transaction["from"]]["count"] += 1
            self.total_transactions += 1
            self.total_amount += transaction["amount"]

        def get_account_transactions(self, address):
            return self.transactions_by_account.get(address, {"total": 0, "count": 0})
