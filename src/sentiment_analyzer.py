import yfinance as yf
from datetime import datetime

class TradeSentimentAnalyzer:
    def __init__(self, tickers):
        self.tickers = tickers
        # Mots-clés simplifiés pour le sentiment (B2C/Swing Trading)
        self.positive_words = ['upgraded', 'buy', 'growth', 'beat', 'bullish', 'positive', 'surge', 'dividend']
        self.negative_words = ['downgraded', 'sell', 'debt', 'miss', 'bearish', 'negative', 'drop', 'inflation', 'risk']

    def get_news_and_sentiment(self, ticker):
        stock = yf.Ticker(ticker)
        news = stock.news
        
        if not news:
            return "Aucune nouvelle récente trouvée."

        sentiment_score = 0
        headlines = []

        for item in news[:5]:  # On analyse les 5 dernières nouvelles
            title = item['title'].lower()
            headlines.append(f"- {item['title']} ({datetime.fromtimestamp(item['provider_publish_time']).strftime('%Y-%m-%d')})")
            
            # Calcul de score très basique
            for word in self.positive_words:
                if word in title: sentiment_score += 1
            for word in self.negative_words:
                if word in title: sentiment_score -= 1

        # Interprétation du score
        if sentiment_score > 0:
            verdict = "POSITIF 🟢"
        elif sentiment_score < 0:
            verdict = "NÉGATIF 🔴 (Prudence)"
        else:
            verdict = "NEUTRE ⚪"

        return {
            "ticker": ticker,
            "verdict": verdict,
            "score": sentiment_score,
            "headlines": headlines
        }

# --- TEST DU SYSTÈME ---
my_tickers = ["NVDA", "COST", "XLE"]
analyzer = TradeSentimentAnalyzer(my_tickers)

print(f"--- ANALYSE DU SENTIMENT ({datetime.now().strftime('%Y-%m-%d')}) ---\n")

for t in my_tickers:
    data = analyzer.get_news_and_sentiment(t)
    print(f"TITRE: {t}")
    print(f"VERDICT: {data['verdict']} (Score: {data['score']})")
    print("DERNIÈRES NOUVELLES:")
    for h in data['headlines']:
        print(h)
    print("-" * 30)