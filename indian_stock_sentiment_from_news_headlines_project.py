# -*- coding: utf-8 -*-
"""test_initial code.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1l2RUDiIbzaX9CoEnqyYVTev7SQ4EAS8M
"""


from bs4 import BeautifulSoup
import requests
from transformers import pipeline
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

# import matplotlib.pyplot as plt
import io
import re
from datetime import timedelta
import numpy as np
import yfinance as yf
import pandas as pd
from dateutil import parser
from io import BytesIO

import warnings

warnings.filterwarnings(
    "ignore", message=".*UnknownTimezoneWarning.*"
)  # Ignore for now (handle time zone if needed)
warnings.filterwarnings(
    "ignore", message=".*torch.utils._pytree._register_pytree_node.*"
)  # Ignore for now (update code later)

warnings.filterwarnings("ignore", message=".*This is a development server.*")


def scrape_news_data(base_url, start_path, from_site, max_pages=9):
    def get_news_items(soup, site):
        if site == "economic_times":
            return soup.find_all("div", class_="eachStory"), lambda item: (
                item.find("h3").get_text(strip=True),
                item.find("time", class_="date-format").get_text(strip=True),
                item.find("p").get_text(strip=True),
            )
        elif site == "moneycontrol":
            return soup.find_all("li", class_="clearfix"), lambda item: (
                item.find("h2").get_text(strip=True),
                item.find("span").get_text(strip=True),
                item.find("p").get_text(strip=True),
            )

    all_news_data = []
    for page in range(max_pages):
        url = f"{base_url}{start_path}" if page == 0 else f"{base_url}{next_page_path}"
        response = requests.get(url)
        if response.status_code != 200:
            break
        soup = BeautifulSoup(response.content, "html.parser")
        news_items, extract_func = get_news_items(soup, from_site)

        for item in news_items:
            data = extract_func(item)
            if all(data):
                all_news_data.append(data)
        if from_site == "moneycontrol":
            next_page_link = soup.find("a", {"data-page": str(page + 2)})
            next_page_path = next_page_link["href"] if next_page_link else None

    return all_news_data


def save_news_data_to_file(news_data, filename):
    with open(filename, "w", encoding="utf-8") as file:
        for headline, date_time, summary in news_data:
            file.write(
                f"Headline: {headline}\nTime: {date_time}\nSummary: {summary}\n\n"
            )


def load_data_from_text(file_path):
    data = []
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.read().strip().split("\n\n")
        for item in content:
            parts = item.split("\n")
            if len(parts) >= 3:  # Check if there are at least 3 parts
                headline = parts[0].replace("Headline: ", "")
                date_time = parts[1].replace("Time: ", "")
                # Combine all remaining parts as summary in case there are extra newlines
                summary = " ".join(parts[2:]).replace("Summary: ", "")
                data.append(
                    {"Date_Time": date_time, "Headline": headline, "Summary": summary}
                )
    return pd.DataFrame(data)


def combine_and_save_dataframes_parquet(df1, df2, output_path):
    combined_df = pd.concat([df1, df2], ignore_index=True)
    combined_df["Date_Time"] = pd.to_datetime(
        combined_df["Date_Time"].apply(lambda x: parser.parse(x))
    )
    combined_df.to_parquet(
        output_path.replace(".xlsx", ".parquet"), index=False, engine="fastparquet"
    )


et_news_data = scrape_news_data(
    "https://economictimes.indiatimes.com", "/markets/stocks/news", "economic_times", 1
)
mc_news_data = scrape_news_data(
    "https://www.moneycontrol.com", "/news/business/stocks/", "moneycontrol", 2
)

save_news_data_to_file(et_news_data, "economic_times_summaries.txt")
save_news_data_to_file(mc_news_data, "moneycontrol.txt")

et_news_df = load_data_from_text("economic_times_summaries.txt")
mc_news_df = load_data_from_text("moneycontrol.txt")

combine_and_save_dataframes_parquet(
    et_news_df, mc_news_df, "combined_summaries.parquet"
)


# Initialize the model and tokenizer once
model_name = "yiyanghkust/finbert-tone"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name)
finbert_pipeline = pipeline("sentiment-analysis", model=model, tokenizer=tokenizer)


def batch_process_sentiments(texts, batch_size=8):
    batched_sentiments = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        sentiments = finbert_pipeline(batch)
        batched_sentiments.extend(sentiments)
    return [s["label"] for s in batched_sentiments]


combined_news_df = pd.read_parquet("combined_summaries.parquet")

combined_news_df["Sentiment"] = batch_process_sentiments(
    combined_news_df["Summary"].tolist()
)


def adjust_sentiment_with_rules(text, predicted_sentiment):
    positive_keywords = [
        "rise",
        "gain",
        "growth",
        "profit",
        "bullish",
        "high",
        "increase",
        "surge",
        "boost",
        "upward",
        "advantage",
    ]
    negative_keywords = [
        "fall",
        "drop",
        "loss",
        "decline",
        "bearish",
        "low",
        "decrease",
        "plunge",
        "downturn",
        "downward",
        "disadvantage",
    ]

    if (
        any(keyword in text.lower() for keyword in positive_keywords)
        and predicted_sentiment != "Positive"
    ):
        return "Positive"
    elif (
        any(keyword in text.lower() for keyword in negative_keywords)
        and predicted_sentiment != "Negative"
    ):
        return "Negative"
    return predicted_sentiment


# Vectorized adjustment of sentiments
combined_news_df["Adjusted_Sentiment"] = combined_news_df.apply(
    lambda row: adjust_sentiment_with_rules(row["Summary"], row["Sentiment"]), axis=1
)

# # Plotting the sentiment distribution
# combined_news_df["Adjusted_Sentiment"].value_counts().plot(
#     kind="bar", title="Sentiment Distribution", xlabel="Sentiment", ylabel="Count"
# ).set_xticklabels(labels=combined_news_df["Adjusted_Sentiment"].unique(), rotation=0)
# plt.tight_layout()
# plt.show()


def clean_company_name(name):
    suffixes = "|".join([" Limited", " Ltd", "BSE", "(BSE)", "NSE", " LTD", " LIMITED"])
    name = re.sub("(" + suffixes + ")$", "", name, flags=re.IGNORECASE).strip()
    return name


def download_and_process_stock_names(file_url):
    response = requests.get(file_url)
    if response.status_code == 200:
        # Use BytesIO for binary data
        stock_names_df = pd.read_parquet(BytesIO(response.content))
        stock_names_df["NAME OF COMPANY"] = stock_names_df["NAME OF COMPANY"].apply(
            clean_company_name
        )
        return stock_names_df.set_index("NAME OF COMPANY")["SYMBOL"].to_dict()
    else:
        print("Failed to download the file.")
        return {}


stock_dict = download_and_process_stock_names(
    "https://drive.google.com/uc?export=download&id=10QllkQfwHwt9zkajuu-mAuXQrPIQ-fFp"
)


# Optimized function to find triggered stocks
def find_triggered_stocks(text, stock_dict):
    triggered_stocks = []
    for name, symbol in stock_dict.items():
        if name in text or symbol in text:
            triggered_stocks.append((name, symbol))
    return triggered_stocks if triggered_stocks else []


# Apply the aggregation function and create new columns with optimization
def aggregate_triggered_stocks(row, stock_dict):
    combined_text = f"{row['Headline']} {row['Summary']}"
    triggered = find_triggered_stocks(combined_text, stock_dict)
    names = ", ".join([t[0] for t in triggered])
    symbols = ", ".join([t[1] for t in triggered])
    return [names, symbols]  # Return a list with two elements


# Vectorization not directly applicable here due to the nature of operations, but minimized repeat calls to improve efficiency
triggered_stocks_results = combined_news_df.apply(
    aggregate_triggered_stocks, args=(stock_dict,), axis=1
)

combined_news_df[["Triggered_Stock_Names", "Triggered_Stock_Symbols"]] = (
    combined_news_df.apply(
        lambda row: pd.Series(aggregate_triggered_stocks(row, stock_dict)), axis=1
    )
)

# Following this, the rest of your operations, like exploding the 'Triggered_Stock_Symbols' column, should work as intended.
df_exploded = combined_news_df.explode("Triggered_Stock_Symbols")


# print(df_exploded)


# Function to clean company names by removing common suffixes
def clean_company_name(name):
    suffixes = [" Limited", " Ltd", "BSE", "(BSE)", "NSE", " LTD", " LIMITED"]
    for suffix in suffixes:
        name = re.sub(suffix + "$", "", name, flags=re.IGNORECASE).strip()
    return name


# Modified function to find stock names or symbols in text and exclude "(BSE)"
def find_triggered_stocks(text, stock_dict):
    triggered_stocks = []
    text_clean = clean_company_name(text)
    for name, symbol in stock_dict.items():
        if clean_company_name(name) in text_clean or symbol in text_clean:
            triggered_stocks.append((name, symbol))
    return triggered_stocks if triggered_stocks else []


# Download the stock names CSV file

file_url = (
    "https://drive.google.com/uc?export=download&id=10QllkQfwHwt9zkajuu-mAuXQrPIQ-fFp"
)
response = requests.get(file_url)

# If the request was successful, load the content into a DataFrame
if response.status_code == 200:
    stock_names_csv = pd.read_parquet(BytesIO(response.content))
    stock_dict = pd.Series(
        stock_names_csv.SYMBOL.values, index=stock_names_csv["NAME OF COMPANY"]
    ).to_dict()
    # Clean the dictionary keys (company names)

    stock_dict = {clean_company_name(k): v for k, v in stock_dict.items()}
else:
    print("Failed to download the file.")
    stock_dict = {}


def aggregate_triggered_stocks(row):
    combined_text = f"{row['Headline']} {row['Summary']}"
    triggered_stocks = find_triggered_stocks(combined_text, stock_dict)
    # Separate names and symbols
    # Exclude "BSE" from symbols and separate names and symbols
    names = ", ".join([name for name, symbol in triggered_stocks])
    symbols = ", ".join(
        [symbol for name, symbol in triggered_stocks if symbol != "BSE"]
    )

    # Replace empty strings with np.nan
    names = names if names else np.nan
    symbols = symbols if symbols else np.nan

    return names, symbols


combined_news_df[["Triggered_Stock_Names", "Triggered_Stock_Symbols"]] = (
    combined_news_df.apply(
        lambda row: pd.Series(aggregate_triggered_stocks(row)), axis=1
    )
)

combined_news_df["Triggered_Stock_Symbols"] = combined_news_df[
    "Triggered_Stock_Symbols"
].str.split(",")

# Then, use `explode` to expand the list into separate rows
df_exploded = combined_news_df.explode("Triggered_Stock_Symbols")

print(df_exploded)


def get_trading_days(data, base_date):
    """
    Identifies the nearest trading days before and after the base_date within the fetched data.
    """
    trading_days = data.index
    before = trading_days[trading_days < base_date]
    after = trading_days[trading_days > base_date]

    before_date = before[-1] if len(before) > 0 else None
    after_date = after[0] if len(after) > 0 else None
    return before_date, base_date, after_date


# data = yf.download(
#     symbol,
#     start=base_date - pd.Timedelta(days=10),
#     end=base_date + pd.Timedelta(days=10),
# )


def get_stock_prices(symbol, base_date):
    if pd.isna(symbol):
        return np.nan, np.nan, np.nan

    symbol += ".NS"
    data = yf.download(
        symbol,
        start=base_date - pd.Timedelta(days=10),
        end=base_date + pd.Timedelta(days=10),
    )

    before_date, present_date, after_date = get_trading_days(data, base_date)

    before_price = data.loc[before_date, "Close"] if before_date else np.nan
    present_price = (
        data.loc[present_date, "Close"] if present_date in data.index else np.nan
    )
    after_price = data.loc[after_date, "Close"] if after_date else np.nan

    return before_price, present_price, after_price


df_exploded["Date_Time"] = pd.to_datetime(df_exploded["Date_Time"])
df_exploded["Date"] = df_exploded["Date_Time"].dt.date
df_exploded["Time"] = df_exploded["Date_Time"].dt.time

# Assuming df_exploded is your DataFrame and 'Date' column is in datetime format
df_exploded["Date"] = pd.to_datetime(df_exploded["Date"])
df_exploded[["News_Day_Before", "News_day", "News_Day_After"]] = df_exploded.apply(
    lambda row: pd.Series(
        get_stock_prices(row["Triggered_Stock_Symbols"], row["Date"])
    ),
    axis=1,
)


# Ensure 'Date_Time' is a datetime column
df_exploded["Date_Time"] = pd.to_datetime(df_exploded["Date_Time"])


# Function to adjust date based on the time
def adjust_date(row):
    cutoff_time = pd.Timedelta(hours=15, minutes=30)
    # Extract time from 'Date_Time' and convert to timedelta for comparison
    news_time = pd.Timedelta(
        hours=row["Date_Time"].hour, minutes=row["Date_Time"].minute
    )
    if news_time > cutoff_time:
        return row["Date_Time"] + pd.Timedelta(days=1)
    else:
        return row["Date_Time"]


# Create 'Targeted_Date' column with adjusted dates
df_exploded["Targeted_Date"] = df_exploded.apply(adjust_date, axis=1).dt.date

# First, ensure 'Targeted_Date' is a datetime object
df_exploded["Targeted_Date"] = pd.to_datetime(df_exploded["Targeted_Date"])

# Calculate 'Price_Day_Before_Targeted' by subtracting one day from 'Targeted_Date'
df_exploded["Price_Day_Before_Targeted"] = df_exploded["Targeted_Date"] - pd.Timedelta(
    days=1
)

print(df_exploded)

df_exploded.to_parquet("final.parquet", index=False, engine="fastparquet")

# Load your Excel file
df = pd.read_parquet("final.parquet")


def calculate_sma(data, window):
    return data.rolling(window=window).mean()


def calculate_ema(data, span):
    return data.ewm(span=span, adjust=False).mean()


def calculate_rsi(data, periods=14):
    delta = data.diff()
    gains = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    losses = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gains / losses
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(data, fast_period=12, slow_period=26, signal_period=9):
    fast_ema = calculate_ema(data, fast_period)
    slow_ema = calculate_ema(data, slow_period)
    macd = fast_ema - slow_ema
    signal = calculate_ema(macd, signal_period)
    return macd, signal


def get_stock_data_and_indicators(symbol, base_date):
    if pd.isna(symbol):
        return [np.nan] * 8  # Return a list of NaN values for the 8 indicator columns

    symbol += ".NS"
    data = yf.download(
        symbol,
        start=base_date - pd.Timedelta(days=200),
        end=base_date + pd.Timedelta(days=10),
    )

    if data.empty:
        return [np.nan] * 8

    # Get the nearest trading days
    before_date, present_date, after_date = get_trading_days(data, base_date)

    # Calculate technical indicators
    sma_10 = calculate_sma(data["Close"], 10).iloc[-1]
    sma_20 = calculate_sma(data["Close"], 20).iloc[-1]
    rsi = calculate_rsi(data["Close"]).iloc[-1]
    macd, macd_signal = calculate_macd(data["Close"])

    # Get the prices for the specified dates
    before_price = data.loc[before_date, "Close"] if before_date else np.nan
    present_price = (
        data.loc[present_date, "Close"] if present_date in data.index else np.nan
    )
    after_price = data.loc[after_date, "Close"] if after_date else np.nan

    # Return all the calculated values
    return [
        before_price,
        present_price,
        after_price,
        sma_10,
        sma_20,
        rsi,
        macd.iloc[-1],
        macd_signal.iloc[-1],
    ]


# Apply the function to each row in the DataFrame
indicator_columns = [
    "News_Day_Before",
    "News_day",
    "News_Day_After",
    "SMA_10",
    "SMA_20",
    "RSI",
    "MACD",
    "MACD_Signal",
]
df_exploded[indicator_columns] = df_exploded.apply(
    lambda row: pd.Series(
        get_stock_data_and_indicators(row["Triggered_Stock_Symbols"], row["Date"])
    ),
    axis=1,
)

for index, row in df.iterrows():
    try:
        symbol = row["Triggered_Stock_Symbols"]
        if pd.notna(symbol):
            symbol += ".NS"
            # Ensure start_date and end_date are actual date values, e.g., '2023-01-01'
            start_date = (
                pd.to_datetime(row["Date"]) - pd.Timedelta(days=200)
            ).strftime("%Y-%m-%d")
            end_date = (pd.to_datetime(row["Date"]) + pd.Timedelta(days=10)).strftime(
                "%Y-%m-%d"
            )
            data = yf.download(symbol, start=start_date, end=end_date)

            if not data.empty:
                df.at[index, "SMA_10"] = calculate_sma(data["Close"], 10).iloc[-1]
                df.at[index, "SMA_50"] = calculate_sma(data["Close"], 50).iloc[-1]
                df.at[index, "RSI"] = calculate_rsi(data["Close"]).iloc[-1]
                macd, signal = calculate_macd(data["Close"])
                df.at[index, "MACD"] = macd.iloc[-1]
                df.at[index, "MACD_Signal"] = signal.iloc[-1]

    except Exception as e:
        print(f"Error processing symbol: {symbol}")
        print(f"Start date: {start_date}, End date: {end_date}")
        print(f"Error message: {e}")

for index, row in df.iterrows():
    if pd.notna(row["Triggered_Stock_Symbols"]):
        indicators = get_stock_data_and_indicators(
            row["Triggered_Stock_Symbols"], row["Date"]
        )
        for i, col in enumerate(indicator_columns):
            df.loc[index, col] = indicators[i]


def interpret_rsi(rsi):
    if rsi > 70:
        return "Overvalued (RSI > 70)"
    elif rsi < 30:
        return "Undervalued (RSI < 30)"
    else:
        return "Neutral"


def interpret_sma(sma_10, sma_20):

    if sma_10 > sma_20:
        return "Bullish Signal (SMA_10 > SMA_20)"
    elif sma_10 < sma_20:
        return "Bearish Signal (SMA_10 < SMA_20)"
    else:
        return "Neutral"


def interpret_macd(macd, signal):

    if macd > signal:
        return "Bullish Signal (MACD > Signal)"
    elif macd < signal:
        return "Bearish Signal (MACD < Signal)"
    else:
        return "Neutral"


df["MACD_Analysis"] = df.apply(
    lambda row: interpret_macd(row["MACD"], row["MACD_Signal"]), axis=1
)

df["SMA_Analysis"] = df.apply(
    lambda row: interpret_sma(row["SMA_10"], row["SMA_20"]), axis=1
)

df["RSI_Analysis"] = df["RSI"].apply(interpret_rsi)

df.to_excel("updated_final.xlsx", index=False)


# Load the existing Excel file
existing_data = pd.read_excel("updated_final.xlsx")
