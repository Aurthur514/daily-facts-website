# CoinSwitch PRO Auto-Trading Bot

This is an advanced auto-trading bot that trades INR pairs on CoinSwitch PRO. It uses technical indicators like RSI and Bollinger Bands to make trading decisions and cross-references data feeds for reliability.

## Installation

To run this bot, you need to have Python 3 installed. You will also need to install the following dependencies:

```bash
pip install requests pandas pandas-ta cryptography
```

## Configuration

The bot requires API keys from CoinSwitch PRO to be able to trade. These keys should be set as environment variables.

You can set the environment variables in your shell like this:

**On macOS and Linux:**
```bash
export API_KEY="YOUR_API_KEY"
export SECRET_KEY="YOUR_SECRET_KEY"
```

**On Windows (Command Prompt):**
```bash
set API_KEY="YOUR_API_KEY"
set SECRET_KEY="YOUR_SECRET_KEY"
```

> **Note:** Never commit your API keys to version control.

## Usage

To start the trading bot, run the following command:

```bash
python trading_bot.py
```

The bot will run continuously, checking for trading opportunities every 5 minutes (300 seconds), as defined by the `TRADING_INTERVAL_SECONDS` variable in the script.

## Disclaimer

Trading cryptocurrencies involves significant risk. This bot is provided as-is, and the author is not responsible for any financial losses you may incur. Use this bot at your own risk. It is highly recommended to test the bot with a small amount of money before using it with a larger balance.
