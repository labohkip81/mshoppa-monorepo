"""Allow a small, display-only subset of HTML in merchant-authored text."""

import re
from html.parser import HTMLParser

import nh3
from rest_framework import serializers

RICH_TAGS = {
    "p",
    "br",
    "div",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "h2",
    "h3",
    "ul",
    "ol",
    "li",
    "blockquote",
    "a",
}
CLEANER = nh3.Cleaner(
    tags=RICH_TAGS,
    clean_content_tags={"script", "style", "iframe", "object", "template", "svg", "math"},
    attributes={"a": {"href", "title"}},
    url_schemes={"http", "https", "mailto", "tel"},
    url_relative="deny",
    link_rel="noopener noreferrer",
)
HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")


class TextContent(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"p", "div", "h2", "h3", "li", "blockquote"}:
            self.parts.append("\n")


def plain_text(value):
    if not HTML_TAG.search(value):
        return value
    parser = TextContent()
    parser.feed(value)
    return "".join(parser.parts).rstrip("\n")


def clean_rich_text(value):
    # Keep plain-text API clients compatible, including literal ampersands and newlines.
    if not HTML_TAG.search(value):
        return value
    clean = CLEANER.clean(value)
    if not HTML_TAG.search(clean):
        clean = "<p>" + clean + "</p>"
    return clean if plain_text(clean).strip() else ""


class RichTextField(serializers.CharField):
    def __init__(self, text_limit, **kwargs):
        self.text_limit = text_limit
        super().__init__(max_length=text_limit * 8 + 4096, **kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        # Bound parser work before sanitizing; CharField validators run afterwards.
        if len(value) > self.max_length:
            self.fail("max_length", max_length=self.max_length)
        value = clean_rich_text(value)
        if len(plain_text(value)) > self.text_limit:
            raise serializers.ValidationError(
                f"Use at most {self.text_limit:,} characters of text."
            )
        return value

    def to_representation(self, value):
        return clean_rich_text(super().to_representation(value))
