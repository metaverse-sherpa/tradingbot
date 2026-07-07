import re

with open("webapp-react/src/components/BacktestsPage.tsx", "r") as f:
    content = f.read()

patch = """
  useEffect(() => {
    if (searchParams.get('run') === 'true' && !loading && !results && !error) {
      runBacktest();
    }
  }, [searchParams, strategy, riskPct, period]);
"""

content = content.replace("  const formatCurrency = (val: number) => {", patch + "\n  const formatCurrency = (val: number) => {")

with open("webapp-react/src/components/BacktestsPage.tsx", "w") as f:
    f.write(content)

