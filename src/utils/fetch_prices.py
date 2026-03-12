import yfinance as yf
import sys
import json

def fetch_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        # 获取实时价格和变化
        data = ticker.history(period="1d")
        if data.empty:
            return {"error": f"No data found for {symbol}"}
        
        current_price = data['Close'].iloc[-1]
        prev_close = ticker.info.get('previousClose', current_price)
        change_percent = ((current_price - prev_close) / prev_close) * 100
        
        return {
            "symbol": symbol,
            "price": round(float(current_price), 2),
            "changePercent": round(float(change_percent), 2),
            "timestamp": data.index[-1].isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No symbol provided"}))
        sys.exit(1)
    
    symbol = sys.argv[1]
    result = fetch_price(symbol)
    print(json.dumps(result))
