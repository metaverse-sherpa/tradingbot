def generate_ssr_html(path):
    # Base layout with Meta tags based on the path
    title = "Sherpa Trading Bot"
    description = "Automated crypto and stock trading bot using Elliott Wave theory."
    
    if path.startswith("/strategies/valkyrie-elite"):
        title = "Valkyrie Elite Strategy | Sherpa Trading Bot"
        description = "High-frequency crypto trading strategy designed for aggressive growth."
    elif path.startswith("/strategies/sherpa-velocity"):
        title = "Sherpa Velocity Strategy | Sherpa Trading Bot"
        description = "Momentum-based stock trading strategy."
    elif path.startswith("/strategies"):
        title = "Trading Strategies | Sherpa Trading Bot"
        description = "Explore our automated trading strategies including Valkyrie Elite and Sherpa Velocity."
    elif path.startswith("/pricing"):
        title = "Pricing | Sherpa Trading Bot"
        description = "View our subscription plans and pricing for automated trading."
        
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <meta name="description" content="{description}">
    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">
    <!-- Twitter -->
    <meta property="twitter:card" content="summary_large_image">
    <meta property="twitter:title" content="{title}">
    <meta property="twitter:description" content="{description}">
</head>
<body>
    <h1>{title}</h1>
    <p>{description}</p>
    <div>
        <!-- This is a server-side rendered page for search engine crawlers. Users should see the React app. -->
        <a href="/strategies">Strategies</a>
        <a href="/strategies/valkyrie-elite">Valkyrie Elite</a>
        <a href="/strategies/sherpa-velocity">Sherpa Velocity</a>
        <a href="/pricing">Pricing</a>
    </div>
</body>
</html>
"""
    return html
