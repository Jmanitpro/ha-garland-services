"""Parse the City of Garland sanitation web pages.

Pure Python (no Home Assistant imports) so it can be unit tested directly.

Two pages are read:

* Holiday Closure Information - one paragraph per holiday, in sentences like
  "Trash, recycling, brush and bulky collections normally scheduled on
  Thursday will be collected on Friday, January 2, 2026." or "... normally
  scheduled on Friday will move to Saturday."
* Reduce, Reuse, Recycle Calendar - links to the annual Blue/Yellow recycling
  calendar (issuu embed + DocumentCenter PDF) whose names carry the year.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urljoin

ALL_SERVICES = frozenset({"trash", "recycling", "brush"})

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")
_WD = "(?:" + "|".join(_WEEKDAYS) + ")"
_MON = "(?:" + "|".join(_MONTHS) + ")"

# "Thursday, January 1, 2026" / "Friday July 3, 2026"
FULL_DATE_RE = re.compile(
    rf"(?P<wd>{_WD}),?\s+(?P<month>{_MON})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<year>\d{{4}})",
    re.IGNORECASE,
)
SHIFT_RE = re.compile(
    rf"normally\s+scheduled\s+(?:on\s+|for\s+)?(?P<orig>{_WD})s?\s+will\s+"
    rf"(?:be\s+collected\s+on|be\s+moved\s+to|move\s+to|be\s+on|shift\s+to)\s+(?P<new>{_WD})"
    rf"(?:,?\s+(?P<month>{_MON})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<year>\d{{4}}))?",
    re.IGNORECASE,
)
NOT_AFFECTED_RE = re.compile(r"(?:will\s+not|won'?t)\s+be\s+affected|no\s+(?:change|delay)", re.IGNORECASE)
HEADER_RE = re.compile(r"^\s*(?P<name>[^\n]{2,60}?)\s+[-–—]\s+")
PAGE_YEAR_RE = re.compile(r"Holiday\s+Service\s+Delays\s+for\s+(\d{4})", re.IGNORECASE)
CALENDAR_LINK_RES = (
    re.compile(r"[?&]d=(?P<year>20\d{2})_(?:recycling|sanitation)_calendar", re.IGNORECASE),
    re.compile(r"DocumentCenter/View/\d+/(?P<year>20\d{2})-?BY-?Calendar", re.IGNORECASE),
    re.compile(r"(?P<year>20\d{2})[^/\"'?]*(?:recycl|BYCalendar|blue[-_ ]?yellow)", re.IGNORECASE),
)


@dataclass(frozen=True)
class HolidayShift:
    """A city-published move of a collection day."""

    original: date
    adjusted: date
    holiday: str
    services: frozenset[str] = ALL_SERVICES

    def as_dict(self) -> dict:
        return {
            "holiday": self.holiday,
            "regular_date": self.original.isoformat(),
            "new_date": self.adjusted.isoformat(),
            "services": sorted(self.services),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HolidayShift":
        return cls(
            date.fromisoformat(data["regular_date"]),
            date.fromisoformat(data["new_date"]),
            data.get("holiday") or "Holiday",
            frozenset(data.get("services") or ALL_SERVICES),
        )


@dataclass(frozen=True)
class HolidayNotice:
    """One holiday paragraph, whether or not collection is affected."""

    holiday: str
    closed: date | None
    collection_affected: bool

    def as_dict(self) -> dict:
        return {
            "holiday": self.holiday,
            "closed": self.closed.isoformat() if self.closed else None,
            "collection_affected": self.collection_affected,
        }


@dataclass
class HolidayFeed:
    page_year: int | None = None
    shifts: list[HolidayShift] = field(default_factory=list)
    notices: list[HolidayNotice] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def covered_years(self) -> set[int]:
        years = {n.closed.year for n in self.notices if n.closed}
        years |= {s.original.year for s in self.shifts}
        if self.page_year:
            years.add(self.page_year)
        return years


class _BlockParser(HTMLParser):
    """Collect text per block element (<p>, <li>, <h1-6>, <div> leaves)."""

    BLOCKS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "div", "section", "article"}
    SKIP = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._buf: list[str] = []
        self._skip = 0

    def _flush(self) -> None:
        text = "".join(self._buf)
        self._buf = []
        lines = [re.sub(r"[ \t\r\f\v\xa0]+", " ", ln).strip() for ln in text.split("\n")]
        text = "\n".join(ln for ln in lines if ln)
        if text:
            self.blocks.append(text)

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "br":
            self._buf.append("\n")
        elif tag in self.BLOCKS:
            self._flush()

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCKS:
            self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush()


def html_blocks(html: str) -> list[str]:
    parser = _BlockParser()
    parser.feed(html)
    parser.close()
    return parser.blocks


def _weekday(name: str) -> int:
    return _WEEKDAYS.index(name.lower())


def _date(month: str, day: str, year: str) -> date:
    return date(int(year), _MONTHS.index(month.lower()) + 1, int(day))


def _services_in(text: str) -> frozenset[str]:
    lowered = text.lower()
    found = {s for s in ALL_SERVICES if s in lowered}
    if "bulky" in lowered:
        found.add("brush")
    return frozenset(found) or ALL_SERVICES


def _sentence_around(text: str, start: int) -> str:
    begin = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start)) + 1
    return text[begin:start]


def parse_holiday_page(html: str) -> HolidayFeed:
    """Parse the Holiday Closure Information page into collection shifts."""
    feed = HolidayFeed()
    blocks = html_blocks(html)
    for block in blocks:
        if feed.page_year is None and (m := PAGE_YEAR_RE.search(block)):
            feed.page_year = int(m.group(1))

    seen: dict[tuple[date, frozenset[str]], HolidayShift] = {}
    for block in blocks:
        header = HEADER_RE.match(block)
        has_shift = SHIFT_RE.search(block) is not None
        unaffected = NOT_AFFECTED_RE.search(block) is not None
        if not header or not (has_shift or unaffected):
            continue
        name = unescape(header.group("name")).strip(" :*")
        dates = []
        for m in FULL_DATE_RE.finditer(block):
            try:
                d = _date(m.group("month"), m.group("day"), m.group("year"))
            except ValueError:
                continue
            if d.weekday() == _weekday(m.group("wd")):
                dates.append(d)
            else:
                feed.warnings.append(f"{name}: weekday does not match {d.isoformat()}")
        closed = dates[0] if dates else None
        feed.notices.append(HolidayNotice(name, closed, has_shift))
        if not has_shift:
            continue

        for m in SHIFT_RE.finditer(block):
            orig_wd, new_wd = _weekday(m.group("orig")), _weekday(m.group("new"))
            delta = (new_wd - orig_wd) % 7
            if delta == 0:
                feed.warnings.append(f"{name}: shift from {m.group('orig')} to the same day ignored")
                continue
            if m.group("year"):
                try:
                    adjusted = _date(m.group("month"), m.group("day"), m.group("year"))
                except ValueError:
                    feed.warnings.append(f"{name}: invalid date in {m.group(0)!r}")
                    continue
                if adjusted.weekday() != new_wd:
                    feed.warnings.append(f"{name}: {adjusted.isoformat()} is not a {m.group('new')}")
                    continue
                original = adjusted - timedelta(days=delta)
            else:
                candidates = [d for d in dates if d.weekday() == orig_wd]
                if candidates:
                    original = candidates[0]
                elif dates:
                    # Same week as the closure date.
                    anchor = dates[0]
                    original = anchor + timedelta(days=(orig_wd - anchor.weekday()) % 7)
                else:
                    feed.warnings.append(f"{name}: no dated closure to anchor {m.group(0)!r}")
                    continue
                adjusted = original + timedelta(days=delta)
            services = _services_in(_sentence_around(block, m.start()))
            shift = HolidayShift(original, adjusted, name, services)
            seen[(original, services)] = shift
    feed.shifts = sorted(seen.values(), key=lambda s: (s.original, sorted(s.services)))
    return feed


def parse_calendar_page(html: str, base_url: str) -> dict[int, list[str]]:
    """Return {year: [urls]} for annual recycling calendars linked on the page."""
    found: dict[int, list[str]] = {}
    for href in re.findall(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", html, re.IGNORECASE):
        href = unescape(href)
        for pattern in CALENDAR_LINK_RES:
            if m := pattern.search(href):
                year = int(m.group("year"))
                url = urljoin(base_url, href)
                if url not in found.setdefault(year, []):
                    found[year].append(url)
                break
    return dict(sorted(found.items()))


def merge_shifts(live: HolidayFeed | None, fallback: list[HolidayShift]) -> list[HolidayShift]:
    """Live page is authoritative for the years it covers; fallback fills the rest."""
    if live is None:
        return sorted(fallback, key=lambda s: s.original)
    covered = live.covered_years
    kept = [s for s in fallback if s.original.year not in covered]
    return sorted(kept + list(live.shifts), key=lambda s: s.original)
