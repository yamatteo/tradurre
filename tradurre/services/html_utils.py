import re
from html import escape, unescape


def strip_html(html: str) -> str:
    """Strip HTML tags and return plain text."""
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", "", text)
    # Decode all named/numeric entities (&amp; &#8217; &#39; ...) rather than
    # dropping the ones we don't special-case -- a deleted entity silently
    # corrupts the translated text.
    text = unescape(text)
    text = text.replace(" ", " ")  # nbsp -> regular space
    return text.strip()


def text_to_html(text: str) -> str:
    """Convert plain text to simple HTML paragraph."""
    return f"<p>{escape(text)}</p>"
