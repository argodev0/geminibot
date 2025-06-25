# exchange_connector.py
# Core functions for connecting to exchanges and fetching data.

import ccxt
import pandas as pd
from decimal import Decimal
import config 

def connect_to_exchange(exchange_id, api_key, api_secret, password=None):
    """
    Establishes a connection with a timeout and specific error handling.
    """
    try:
        exchange_class = getattr(ccxt, exchange_id)
        params = {
            'apiKey': api_key, 
            'secret': api_secret,
            'timeout': 30000, # 30-second timeout for requests
        }
        if password:
            params['password'] = password
            
        exchange = exchange_class(params)
        exchange.load_markets() # Network call to verify connection
        return exchange
    except ccxt.NetworkError as e:
        # Handle network errors (e.g., timeout, DNS issues)
        print(f"NetworkError connecting to {exchange_id}: {e}")
        return None
    except ccxt.AuthenticationError as e:
        # Handle invalid API key errors
        print(f"AuthenticationError connecting to {exchange_id}: {e}")
        return None
    except Exception as e:
        # Handle any other unexpected errors during connection
        print(f"An unexpected error occurred connecting to {exchange_id}: {e}")
        return None

def get_account_data(exchange, account_type_params=None, account_name=""):
    """
    Retrieves, processes, and returns account balance data and USD valuation.
    """
    if not exchange:
        return {'error': f"Could not establish a connection for {account_name}.", 'account_name': account_name}

    try:
        balance = exchange.fetch_balance(params=account_type_params or {})
        non_zero_balances = [
            {'asset': currency, 'total': data['total']}
            for currency, data in balance.items()
            if isinstance(data, dict) and 'total' in data and data['total'] > 0
        ]
        if not non_zero_balances:
            return {'account_name': account_name, 'exchange_name': exchange.name, 'balances_df': pd.DataFrame(), 'total_usd': '0.00', 'error': None}

        total_usd_value = Decimal('0.0')
        balance_details = []
        for asset_balance in non_zero_balances:
            asset = asset_balance['asset']
            total = Decimal(str(asset_balance['total']))
            usd_value, price = Decimal('0.0'), 'N/A'
            if asset in ['USD', 'USDT', 'USDC', 'BUSD', 'DAI']:
                price, usd_value = Decimal('1.0'), total
            else:
                for quote_currency in ['USDT', 'USD', 'BUSD']:
                    try:
                        ticker = exchange.fetch_ticker(f'{asset}/{quote_currency}')
                        price = Decimal(str(ticker['last']))
                        usd_value = total * price
                        break
                    except Exception: continue
            if isinstance(price, Decimal): total_usd_value += usd_value
            balance_details.append({'Asset': asset, 'Total': f"{total:,.8f}".rstrip('0').rstrip('.'), 'Price (USD)': f"${price:,.4f}" if isinstance(price, Decimal) else price, 'Value (USD)': f"${usd_value:,.2f}"})
        
        return {'account_name': account_name, 'exchange_name': exchange.name, 'balances_df': pd.DataFrame(balance_details), 'total_usd': f"{total_usd_value:,.2f}", 'error': None}
    except Exception as e:
        return {'account_name': account_name, 'exchange_name': getattr(exchange, 'name', 'Unknown'), 'error': str(e)}

def get_trade_history(exchange, symbol=None, limit=50):
    """
    Retrieves recent trade history from a single exchange.
    """
    if not exchange: return None
    try:
        if not exchange.has['fetchMyTrades']:
            return pd.DataFrame([{'error': f"{exchange.name} does not support fetching trade history."}])
        
        trades = exchange.fetch_my_trades(symbol=symbol, limit=limit)
        if not trades: return pd.DataFrame()

        trade_details = [{
            'Timestamp': trade['timestamp'], # Keep as raw ms for sorting
            'Symbol': trade['symbol'],
            'Exchange': exchange.name.split(' ')[0], # e.g., 'Binance' from 'Binance USD-M'
            'Side': trade['side'].upper(),
            'Price': trade['price'],
            'Amount': trade['amount'],
            'Fee': f"{trade['fee']['cost']:.6f} {trade['fee']['currency']}",
            'Total (USD)': (Decimal(str(trade['price'])) * Decimal(str(trade['amount'])))
        } for trade in trades]

        return pd.DataFrame(trade_details)
    except ccxt.ExchangeError as e:
        return pd.DataFrame([{'error': f"Exchange Error fetching trades: {e}"}])
    except Exception as e:
        return pd.DataFrame([{'error': str(e)}])
