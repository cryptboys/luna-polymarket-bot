# Luna Polymarket Trading Bot

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template)

Conservative & Self-Evolving Automated Trading for Polymarket Prediction Markets.

## 🌙 Features

- **Phase-Based Strategy**: 5% → 25% position sizing
- **Risk Management**: 20% daily drawdown limit
- **Self-Evolving**: Learns from trade history
- **SQLite Memory**: Persistent tracking
- **Docker Deploy**: Easy cloud deployment

## 🚀 Quick Deploy

### Railway (Recommended)

1. Click "Deploy on Railway" button above
2. Add environment variables (see below)
3. Deploy!

### Environment Variables

```env
# Required
POLY_PRIVATE_KEY=0x...
POLY_API_KEY=...
POLY_API_SECRET=...
POLY_PASSPHRASE=...

# Trading Config
INITIAL_CAPITAL=5.0
START_PHASE=1
MAX_DAILY_LOSS=0.20
CHECK_INTERVAL_MINUTES=5
```

## 📊 Strategy

| Phase | Max Position | Min Confidence |
|-------|--------------|----------------|
| 1 | 5% | 80% |
| 2 | 10% | 75% |
| 3 | 15% | 70% |
| 4 | 25% | 65% |

## 🛡️ Risk Limits

- Daily drawdown: 20% max
- Min liquidity: $10k per market
- Price filter: Avoid <0.05 or >0.95

## 📝 License

MIT - For educational purposes.
