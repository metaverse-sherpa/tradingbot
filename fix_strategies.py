import re

with open("webapp-react/src/components/StrategiesPage.tsx", "r") as f:
    content = f.read()

# Remove Mean Reversion
content = re.sub(r'\{\s*name: "Mean Reversion Scalper",.*?drawdown: "Optimized for 1\.0% risk, maintaining a safe drawdown of ~21\.9%\.",\s*\},', '', content, flags=re.DOTALL)

# Add History to icons
content = content.replace("import { BookOpen, Shield, TrendingUp, BarChart2 } from 'lucide-react';", "import { BookOpen, Shield, TrendingUp, BarChart2, History, ZoomIn } from 'lucide-react';")

# We want to change the rendering loop to show stats and infographic if they exist.
# Wait, I'll just rewrite the whole file because it's only 86 lines and I want to redesign the cards to include stats.
