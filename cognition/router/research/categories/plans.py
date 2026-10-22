"""💳 Subscriptions — Subscription plans: quota meters and the tokens each plan really carried (cost price per token)."""
LABEL = ("Abonnements", "Subscriptions")
ICON = "💳"
# source kind -> parts to read (None = the whole source)
SOURCES = {}
EXTRA = "subscriptions"   # not a snapshot source: research.plans refreshes the meters and usage

