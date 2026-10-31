import pandas as pd
import yfinance as yf
import time
import logging

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def enrich_results_with_fundamentals(input_path: str, output_path: str):
    """
    Reads the backtest results CSV, fetches fundamental data from Yahoo Finance,
    and writes an enriched CSV.
    """
    logger.info(f"Reading input file: {input_path}")
    try:
        df = pd.read_csv(input_path)
    except FileNotFoundError:
        logger.error(f"Could not find {input_path}")
        return

    # Initialize new columns
    df['company_name'] = 'Unknown'
    df['sector'] = 'Unknown'
    df['industry'] = 'Unknown'
    df['ltp'] = 0.0
    df['avg_volume'] = 0
    df['turnover_cr'] = 0.0     # Daily turnover in Crores
    df['market_cap_cr'] = 0.0   # Market capitalization in Crores
    
    total_symbols = len(df)
    
    for index, row in df.iterrows():
        raw_symbol = row['instrument']
        
        # Convert "NSE:RELIANCE" -> "RELIANCE.NS" for Yahoo Finance
        if raw_symbol.startswith("NSE:"):
            yf_ticker = raw_symbol.replace("NSE:", "") + ".NS"
        else:
            yf_ticker = raw_symbol + ".NS"
            
        logger.info(f"[{index + 1}/{total_symbols}] Fetching data for {yf_ticker}...")
        
        try:
            ticker = yf.Ticker(yf_ticker)
            info = ticker.info
            
            # 1. Text Properties
            df.at[index, 'company_name'] = info.get('longName', 'N/A')
            df.at[index, 'sector'] = info.get('sector', 'N/A')
            df.at[index, 'industry'] = info.get('industry', 'N/A')
            
            # 2. Numerical Properties
            ltp = info.get('currentPrice', info.get('regularMarketPreviousClose', 0.0))
            avg_vol = info.get('averageVolume', 0)
            market_cap = info.get('marketCap', 0)
            
            df.at[index, 'ltp'] = ltp
            df.at[index, 'avg_volume'] = avg_vol
            
            # 3. Calculate Turnover and Market Cap in Crores (Value / 10,000,000)
            turnover = (ltp * avg_vol)
            df.at[index, 'turnover_cr'] = round(turnover / 10_000_000, 2)
            df.at[index, 'market_cap_cr'] = round(market_cap / 10_000_000, 2) if market_cap else 0.0
            
        except Exception as e:
            logger.warning(f"Failed to fetch data for {yf_ticker}: {e}")
            
        # Polite delay to prevent rate-limiting from Yahoo Finance
        time.sleep(0.5)

    # Save to new CSV
    df.to_csv(output_path, index=False)
    logger.info(f"Successfully wrote enriched data to {output_path}")

if __name__ == "__main__":
    INPUT_FILE = "./results_final.csv"
    OUTPUT_FILE = "./results_final_enriched.csv"
    
    enrich_results_with_fundamentals(INPUT_FILE, OUTPUT_FILE)