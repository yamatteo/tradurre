import re
from html import escape


def strip_html(html: str) -> str:
    """Strip HTML tags and return plain text."""
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", "", text)
    return text.strip()


def text_to_html(text: str) -> str:
    """Convert plain text to simple HTML paragraph."""
    return f"<p>{escape(text)}</p>"
