"""Alpaca paper-trading adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from trading_app.alpaca_credentials import (
    alpaca_paper_boundary_violations,
    resolve_alpaca_credentials,
)
from trading_app.broker.models import (
    BrokerOrderState,
    BrokerPortfolioState,
    BrokerPositionState,
    aware_datetime,
)
from trading_app.schemas import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    validate_symbol,
)


class AlpacaPaperBrokerAdapter:
    """Translate project orders into Alpaca paper-trading API requests."""

    provider = "alpaca-paper"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        secret_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        _require_live_trading_disabled()
        if client is not None:
            self._client = client
            return

        resolved_api_key, resolved_secret_key = resolve_alpaca_credentials(
            api_key=api_key,
            secret_key=secret_key,
        )

        from alpaca.trading.client import TradingClient

        self._client = TradingClient(
            api_key=resolved_api_key,
            secret_key=resolved_secret_key,
            paper=True,
        )

    def submit_order(self, order: Order) -> BrokerOrderState:
        request = _to_alpaca_order_request(order)
        broker_order = self._client.submit_order(order_data=request)
        return _broker_order_state(broker_order, provider=self.provider)

    def get_order(self, broker_order_id: str) -> BrokerOrderState:
        broker_order = self._client.get_order_by_id(broker_order_id)
        return _broker_order_state(broker_order, provider=self.provider)

    def list_orders(
        self,
        status: OrderStatus | None = None,
        *,
        after: datetime | None = None,
        until: datetime | None = None,
        symbols: tuple[str, ...] | None = None,
        limit: int | None = None,
    ) -> tuple[BrokerOrderState, ...]:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        query_status = QueryOrderStatus.ALL
        if status in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}:
            query_status = QueryOrderStatus.OPEN
        validated_symbols = (
            tuple(validate_symbol(symbol) for symbol in symbols) if symbols else None
        )
        request = GetOrdersRequest(
            status=query_status,
            limit=limit,
            after=after,
            until=until,
            symbols=list(validated_symbols) if validated_symbols else None,
        )
        orders = self._client.get_orders(filter=request)
        mapped = tuple(
            _broker_order_state(order, provider=self.provider) for order in orders
        )
        if status is None or query_status == QueryOrderStatus.OPEN:
            return mapped
        return tuple(order for order in mapped if order.status == status)

    def cancel_order(self, broker_order_id: str, canceled_at=None) -> BrokerOrderState:
        self._client.cancel_order_by_id(order_id=broker_order_id)
        return self.get_order(broker_order_id)

    def get_portfolio(self, as_of: datetime) -> BrokerPortfolioState:
        account = self._client.get_account()
        positions = self._client.get_all_positions()
        return BrokerPortfolioState(
            cash=_decimal_value(account, "cash"),
            buying_power=_optional_decimal_value(account, "buying_power"),
            account_id=_optional_string_value(account, "id")
            or _optional_string_value(account, "account_number"),
            positions=tuple(
                BrokerPositionState(
                    symbol=_string_value(position, "symbol"),
                    quantity=_decimal_value(position, "qty"),
                    average_entry_price=_decimal_value(position, "avg_entry_price"),
                    market_value=_optional_decimal_value(position, "market_value"),
                    current_price=_optional_decimal_value(position, "current_price"),
                )
                for position in positions
            ),
            as_of=as_of,
            provider=self.provider,
        )


class AlpacaLiveBrokerAdapter(AlpacaPaperBrokerAdapter):
    """Disabled-by-default Alpaca live adapter scaffold."""

    provider = "alpaca-live"
    confirmation_phrase = "I_UNDERSTAND_LIVE_RISK"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        secret_key: str | None = None,
        client: Any | None = None,
        live_trading_enabled: bool = False,
        explicit_confirmation: str | None = None,
    ) -> None:
        if not live_trading_enabled:
            raise ValueError("live trading adapter is disabled by default")
        if explicit_confirmation != self.confirmation_phrase:
            raise ValueError("explicit live-risk confirmation is required")
        if client is not None:
            self._client = client
            return

        resolved_api_key, resolved_secret_key = resolve_alpaca_credentials(
            api_key=api_key,
            secret_key=secret_key,
        )

        from alpaca.trading.client import TradingClient

        self._client = TradingClient(
            api_key=resolved_api_key,
            secret_key=resolved_secret_key,
            paper=False,
        )


def _require_live_trading_disabled() -> None:
    violations = alpaca_paper_boundary_violations()
    if violations:
        raise ValueError(
            "Alpaca live-trading flags and live endpoint overrides must be unset "
            f"before creating the Alpaca paper broker: {', '.join(violations)}"
        )


def _to_alpaca_order_request(order: Order):
    from alpaca.trading.enums import OrderSide as AlpacaOrderSide
    from alpaca.trading.enums import OrderType as AlpacaOrderType
    from alpaca.trading.enums import TimeInForce
    from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

    side = AlpacaOrderSide.BUY if order.side == OrderSide.BUY else AlpacaOrderSide.SELL
    common = {
        "symbol": order.symbol,
        "qty": float(order.quantity),
        "side": side,
        "time_in_force": TimeInForce.DAY,
        "client_order_id": order.id,
    }
    if order.order_type == OrderType.MARKET:
        return MarketOrderRequest(type=AlpacaOrderType.MARKET, **common)
    if order.limit_price is None:
        raise ValueError("limit orders require limit_price")
    return LimitOrderRequest(
        type=AlpacaOrderType.LIMIT,
        limit_price=float(order.limit_price),
        **common,
    )


def _broker_order_state(raw_order: Any, *, provider: str) -> BrokerOrderState:
    submitted_at = (
        aware_datetime(_value(raw_order, "submitted_at"))
        or aware_datetime(_value(raw_order, "created_at"))
        or datetime.now(tz=UTC)
    )
    provider_status = _string_value(raw_order, "status")
    return BrokerOrderState(
        broker_order_id=_string_value(raw_order, "id"),
        client_order_id=_optional_string_value(raw_order, "client_order_id"),
        symbol=_string_value(raw_order, "symbol"),
        side=_order_side(_string_value(raw_order, "side")),
        order_type=_order_type(_string_value(raw_order, "type")),
        quantity=_decimal_value(raw_order, "qty"),
        filled_quantity=_optional_decimal_value(raw_order, "filled_qty")
        or Decimal("0"),
        status=_order_status(provider_status),
        submitted_at=submitted_at,
        updated_at=aware_datetime(_value(raw_order, "updated_at")),
        limit_price=_optional_decimal_value(raw_order, "limit_price"),
        average_fill_price=_optional_decimal_value(raw_order, "filled_avg_price"),
        provider=provider,
        provider_status=provider_status,
    )


def _order_side(value: str) -> OrderSide:
    normalized = value.upper()
    if normalized == OrderSide.BUY.value:
        return OrderSide.BUY
    if normalized == OrderSide.SELL.value:
        return OrderSide.SELL
    raise ValueError(f"unsupported Alpaca order side: {value}")


def _order_type(value: str) -> OrderType:
    normalized = value.upper()
    if normalized == OrderType.MARKET.value:
        return OrderType.MARKET
    if normalized == OrderType.LIMIT.value:
        return OrderType.LIMIT
    raise ValueError(f"unsupported Alpaca order type: {value}")


def _order_status(value: str) -> OrderStatus:
    normalized = value.lower()
    if normalized in {"new", "accepted", "pending_new", "accepted_for_bidding"}:
        return OrderStatus.NEW
    if normalized == "partially_filled":
        return OrderStatus.PARTIALLY_FILLED
    if normalized == "filled":
        return OrderStatus.FILLED
    if normalized in {"canceled", "expired", "done_for_day"}:
        return OrderStatus.CANCELED
    if normalized in {"rejected", "stopped", "suspended"}:
        return OrderStatus.REJECTED
    return OrderStatus.NEW


def _value(raw: Any, name: str) -> Any:
    if isinstance(raw, dict):
        return raw.get(name)
    return getattr(raw, name, None)


def _string_value(raw: Any, name: str) -> str:
    value = _value(raw, name)
    if value is None:
        raise ValueError(f"missing broker field: {name}")
    return str(value)


def _optional_string_value(raw: Any, name: str) -> str | None:
    value = _value(raw, name)
    return None if value is None else str(value)


def _decimal_value(raw: Any, name: str) -> Decimal:
    value = _value(raw, name)
    if value is None:
        raise ValueError(f"missing broker field: {name}")
    return Decimal(str(value))


def _optional_decimal_value(raw: Any, name: str) -> Decimal | None:
    value = _value(raw, name)
    if value in {None, ""}:
        return None
    return Decimal(str(value))
