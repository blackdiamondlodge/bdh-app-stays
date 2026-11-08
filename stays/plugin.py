from bdh_sdk import PluginSpec

# No tiles or pages: the app only tells the hub when guests are staying, which
# switches the homepage to guest mode.
spec = PluginSpec(
    id="stays",
    app="stays",
    stay="stays.homepage.current_stay",
)
