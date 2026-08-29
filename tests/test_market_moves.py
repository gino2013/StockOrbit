import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.analytics.market_moves import classify_sentiment


def demo():
    assert classify_sentiment("Nvidia tops Q2 expectations on revenue of $96.2 billion") == "bullish"
    assert classify_sentiment("Stock plunges after earnings miss and weak guidance") == "bearish"
    assert classify_sentiment("Gold ETF Rally Gains Momentum: Will It Sustain?") == "bullish"
    assert classify_sentiment("Company announces new product lineup for next year") == "neutral"
    # mixed signal, roughly equal hits either way -> stays neutral rather than guessing
    assert classify_sentiment("Stock rises then falls on mixed earnings report") == "neutral"


if __name__ == "__main__":
    demo()
    print("OK")
