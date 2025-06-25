# app.py
# Main web server with routes for all pages.

from flask import Flask, render_template, url_for, request
from markupsafe import Markup
import exchange_connector
import config
from datetime import datetime
from termcolor import colored
import os
import pandas as pd
from decimal import Decimal

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, 'templates')
app = Flask(__name__, template_folder=TEMPLATE_DIR)

event_logs = []

def add_log(message, level='info'):
    """Adds a timestamped message to the event log and prints to terminal."""
    global event_logs
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_colors = {'info': 'cyan', 'success': 'green', 'warning': 'yellow', 'error': 'red'}
    print(colored(f"[{now}] [{level.upper()}] {message}", log_colors.get(level, 'white')))
    event_logs.append({'timestamp': now, 'message': message, 'level': level})

@app.route('/')
def dashboard():
    """
    Main route to fetch all data and render the dashboard.
    """
    global event_logs; event_logs = []
    add_log("Dashboard refresh requested.")
    accounts_data = []

    # --- Binance Operations ---
    add_log("Attempting to connect to Binance (Spot/Funding)...")
    binance_spot_conn = exchange_connector.connect_to_exchange('binance', config.BINANCE_API_KEY, config.BINANCE_API_SECRET)
    if binance_spot_conn:
        add_log("Binance connection successful. Fetching data...", 'success')
        accounts_data.append(exchange_connector.get_account_data(binance_spot_conn, account_name="Spot"))
        accounts_data.append(exchange_connector.get_account_data(binance_spot_conn, {'type': 'funding'}, account_name="Funding"))
    else:
        add_log("Failed to connect to Binance. Check API keys and permissions.", 'error')
        accounts_data.append({'error': 'Connection failed.', 'account_name': 'Binance Accounts', 'exchange_name': 'Binance'})

    add_log("Attempting to connect to Binance Futures...")
    binance_futures_conn = exchange_connector.connect_to_exchange('binanceusdm', config.BINANCE_API_KEY, config.BINANCE_API_SECRET)
    if binance_futures_conn:
        add_log("Binance Futures connection successful. Fetching data...", 'success')
        accounts_data.append(exchange_connector.get_account_data(binance_futures_conn, account_name="USD-M Futures"))
    else:
        add_log("Failed to connect to Binance Futures.", 'error')
        accounts_data.append({'error': 'Connection failed.', 'account_name': 'USD-M Futures', 'exchange_name': 'Binance'})

    # --- KuCoin Operations ---
    add_log("Attempting to connect to KuCoin (Main/Trading)...")
    kucoin_spot_conn = exchange_connector.connect_to_exchange('kucoin', config.KUCOIN_API_KEY, config.KUCOIN_API_SECRET, config.KUCOIN_API_PASSPHRASE)
    if kucoin_spot_conn:
        add_log("KuCoin connection successful. Fetching data...", 'success')
        accounts_data.append(exchange_connector.get_account_data(kucoin_spot_conn, {'type': 'main'}, account_name="Main (Funding)"))
        accounts_data.append(exchange_connector.get_account_data(kucoin_spot_conn, {'type': 'trade'}, account_name="Trading"))
    else:
        add_log("Failed to connect to KuCoin. Check API keys and passphrase.", 'error')
        accounts_data.append({'error': 'Connection failed.', 'account_name': 'KuCoin Accounts', 'exchange_name': 'KuCoin'})

    add_log("Attempting to connect to KuCoin Futures...")
    kucoin_futures_conn = exchange_connector.connect_to_exchange('kucoinfutures', config.KUCOIN_API_KEY, config.KUCOIN_API_SECRET, config.KUCOIN_API_PASSPHRASE)
    if kucoin_futures_conn:
        add_log("KuCoin Futures connection successful. Fetching data...", 'success')
        accounts_data.append(exchange_connector.get_account_data(kucoin_futures_conn, account_name="Futures"))
    else:
        add_log("Failed to connect to KuCoin Futures.", 'error')
        accounts_data.append({'error': 'Connection failed.', 'account_name': 'Futures', 'exchange_name': 'KuCoin'})

    for account in accounts_data:
        if 'balances_df' in account and not account['balances_df'].empty:
            account['balances_html'] = Markup(account['balances_df'].to_html(classes='table', index=False, border=0))
        elif 'balances_df' in account:
            account['balances_html'] = Markup("<p class='text-sm text-text-secondary px-5'>No assets found.</p>")
    
    add_log("Data fetch complete. Rendering page.", 'success')
    return render_template('index.html', accounts_data=accounts_data, event_logs=event_logs)

@app.route('/trade-history')
def trade_history():
    add_log("Trade history page requested.")
    all_trades = []
    connections = [
        exchange_connector.connect_to_exchange('binance', config.BINANCE_API_KEY, config.BINANCE_API_SECRET),
        exchange_connector.connect_to_exchange('binanceusdm', config.BINANCE_API_KEY, config.BINANCE_API_SECRET),
        exchange_connector.connect_to_exchange('kucoin', config.KUCOIN_API_KEY, config.KUCOIN_API_SECRET, config.KUCOIN_API_PASSPHRASE),
        exchange_connector.connect_to_exchange('kucoinfutures', config.KUCOIN_API_KEY, config.KUCOIN_API_SECRET, config.KUCOIN_API_PASSPHRASE)
    ]

    for conn in connections:
        if conn:
            add_log(f"Fetching trades from {conn.name}...")
            trades = exchange_connector.get_trade_history(conn)
            if trades is not None and not trades.empty and 'error' not in trades.columns:
                all_trades.append(trades)
    
    history_html = ""
    if not all_trades:
        history_html = "<p class='text-text-secondary'>Could not fetch trade history from any exchange.</p>"
    else:
        combined_df = pd.concat(all_trades, ignore_index=True)
        sort_by = request.args.get('sort_by', 'date')

        if sort_by == 'symbol':
            combined_df.sort_values(by=['Symbol', 'Timestamp'], ascending=[True, False], inplace=True)
        else: 
            combined_df.sort_values(by='Timestamp', ascending=False, inplace=True)

        combined_df['Timestamp'] = pd.to_datetime(combined_df['Timestamp'], unit='ms').dt.strftime('%Y-%m-%d %H:%M:%S')
        for col in ['Price', 'Amount', 'Total (USD)']:
            combined_df[col] = combined_df[col].apply(lambda x: f"{Decimal(str(x)):,.6f}".rstrip('0').rstrip('.'))
        
        history_html = Markup(combined_df.to_html(classes='table', index=False, border=0))

    return render_template('trade_history.html', history_html=history_html, sort_by=sort_by)

@app.route('/tradingview')
def tradingview_chart():
    return render_template('tradingview.html')

@app.route('/strategy-tester')
def strategy_tester():
    return render_template('strategy_tester.html')

if __name__ == '__main__':
    app.run(debug=True, port=5500)
