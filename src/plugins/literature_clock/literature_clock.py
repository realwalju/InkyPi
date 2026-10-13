import logging
import os
from datetime import datetime
import pytz

from utils.app_utils import get_fonts
from plugins.base_plugin.base_plugin import BasePlugin

from .quote_picker import resolve_with_fallback, sanitize, pick_quote, wrap_highlight
from .dataset import ensure_dataset

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "US/Eastern"
ATTRIBUTION_MAX = 55


def _size_tier(n: int) -> int:
    if n <= 80:
        return 1
    if n <= 160:
        return 2
    if n <= 260:
        return 3
    if n <= 380:
        return 4
    return 5


def _seed_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d-%H%M")


class LiteratureClock(BasePlugin):
    def generate_settings_template(self):
        params = super().generate_settings_template()
        params["style_settings"] = True
        # get_fonts() returns one dict per font *variant*, keyed by "font_family"
        # (no "name" key). Dedupe to unique family names for the dropdown.
        params["available_fonts"] = sorted({f["font_family"] for f in get_fonts()})
        return params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        tz_name = device_config.get_config("timezone") or DEFAULT_TIMEZONE
        now = datetime.now(pytz.timezone(tz_name))
        hhmm = now.strftime("%H:%M")

        csv_path = os.path.join(self.get_plugin_dir("data"), "litclock_annotated.csv")
        try:
            ensure_dataset(csv_path)
        except FileNotFoundError as exc:
            logger.error("Literature clock dataset missing: %s", exc)
            raise RuntimeError("Literature clock dataset unavailable.") from exc

        allow_nsfw = settings.get("allow_nsfw") in ("on", "true", True)
        rows, _used_time = resolve_with_fallback(csv_path, hhmm, allow_nsfw=allow_nsfw)

        if not rows:
            return self._render_no_quote(dimensions, hhmm, settings)

        strategy = settings.get("quote_selection") or "shortest"
        chosen = pick_quote(rows, strategy=strategy, seed_key=_seed_key(now))

        quote = sanitize(chosen["full_quote"])
        time_human = sanitize(chosen["time_human"])
        quote_html = wrap_highlight(quote, time_human)

        attribution = ""
        if settings.get("show_attribution", "on") in ("on", "true", True):
            book = sanitize(chosen.get("book_title", ""))
            author = sanitize(chosen.get("author_name", ""))
            attribution = f"— {book}, {author}"
            if len(attribution) > ATTRIBUTION_MAX:
                attribution = attribution[: ATTRIBUTION_MAX - 1] + "…"

        template_params = {
            "quote_html": quote_html,
            "attribution": attribution,
            "show_attribution": bool(attribution),
            "size_tier": _size_tier(len(quote)),
            "font_family": settings.get("font_family") or "serif",
            "highlight_style": settings.get("highlight_style") or "bold",
            "highlight_color": settings.get("highlight_color") or "#c00",
            "plugin_settings": settings,
        }
        return self.render_image(
            dimensions,
            "literature_clock.html",
            "literature_clock.css",
            template_params,
        )

    def _render_no_quote(self, dimensions, hhmm, settings):
        template_params = {
            "quote_html": f"It is {hhmm}.",
            "attribution": "No quote for this minute",
            "show_attribution": True,
            "size_tier": 1,
            "font_family": settings.get("font_family") or "serif",
            "highlight_style": settings.get("highlight_style") or "bold",
            "highlight_color": settings.get("highlight_color") or "#c00",
            "plugin_settings": settings,
        }
        return self.render_image(
            dimensions,
            "literature_clock.html",
            "literature_clock.css",
            template_params,
        )
