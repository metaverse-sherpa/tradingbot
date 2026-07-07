import re

with open("webapp-react/src/components/BacktestsPage.tsx", "r") as f:
    content = f.read()

# I need to insert a useEffect that triggers runBacktest.
# Actually, I can just find where runBacktest is defined.
# I'll just use a small modification in Settings.tsx first.

with open("webapp-react/src/components/Settings.tsx", "r") as f:
    settings = f.read()

settings = settings.replace("navigate(`/backtests?strategy=${encodeURIComponent(user?.active_crypto_strategy || 'Valkyrie Elite Scalper')}&risk=${riskPct}`)", "navigate(`/backtests?strategy=${encodeURIComponent(user?.active_crypto_strategy || 'Valkyrie Elite Scalper')}&risk=${riskPct}&run=true`)")
settings = settings.replace("navigate(`/backtests?strategy=${encodeURIComponent(user?.active_stock_strategy || 'Sherpa Velocity Pullback')}&risk=${stockRiskPct}`)", "navigate(`/backtests?strategy=${encodeURIComponent(user?.active_stock_strategy || 'Sherpa Velocity Pullback')}&risk=${stockRiskPct}&run=true`)")

with open("webapp-react/src/components/Settings.tsx", "w") as f:
    f.write(settings)

