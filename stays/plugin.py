from bdh_sdk import PluginSpec

# No tiles or pages: the app tells the hub when guests (or the owners) are
# staying, which switches the homepage mode, and provides the lodge card.
spec = PluginSpec(
    id="stays",
    app="stays",
    stay="stays.homepage.current_stay",
    card="stays.card.lodge_card",
)
