"""Who a visit is from: the site's own checks, a bot, or a person.

Classify at read time, not when the visit is stored: keep every visit raw, and the lists here can
be refreshed and the whole history read again under the new lists without rewriting a row.

A visit is classified in this order:

    own     a user agent of the site's own checks (the pattern you give), or any visit from an
            address one of those checks came from that same day
    bot     a crawler or script by its user agent, an empty agent, a phone too old to be in use, an
            address in a cloud or hosting network, or a known referrer-spam host
    person  everything else

Your own address is learned from the visits, never configured. When your uptime or render checks
run from the same machine as your tests and your own browser, the address they came from on a day
is that machine's address that day, and a test run there that sends an ordinary agent (Playwright's
"Desktop Chrome" sends a Windows one) is yours too. Reading it per day keeps it right when the
address changes.

The address test reads a list of cloud and hosting IPv4 ranges (data/datacenter_nets.txt), built
from a curated set of cloud and hosting ASNs (data/datacenter_asns.txt) against a public IP-to-ASN
dataset by `realvisits refresh`. CDN and consumer-VPN networks that front real people (such as
Cloudflare) are left out of that set on purpose, so a real visitor behind one still counts as a
person.

Standard library only.
"""
from __future__ import annotations

import bisect
import re
from pathlib import Path
from typing import Iterable, Optional, Pattern, Union
from urllib.parse import urlsplit

OWN, BOT, PERSON = "own", "bot", "person"

#: a bot by its user agent: crawlers, scripts, HTTP libraries, headless browsers, monitors, previews
BOT_AGENT_RE = re.compile(
    r"(bot|crawl|spider|slurp|curl|wget|python|httpx|go-http|java/|okhttp|axios|"
    r"node-fetch|headless|lighthouse|pagespeed|uptime|monitor|pingdom|statuscake|censys|"
    r"scan|preview|facebookexternalhit|embedly)", re.I)

# A phone agent naming a system no phone in use still runs. "iPhone OS 13_2_3" is Chrome DevTools'
# default iPhone emulation, and "Android 5.0" a common crawler disguise. Desktop versions are no
# signal: every current Mac browser sends "Mac OS X 10_15_7" and every Windows one "Windows NT 10.0",
# frozen on purpose, and Chrome on Android sends "Android 10; K" whatever the phone runs.
IOS_RE = re.compile(r"\b(?:iPhone|CPU) OS (\d+)_")
ANDROID_RE = re.compile(r"\bAndroid (\d+)(?=[.;)])")
#: the newest iOS and Android major versions that count as too old to be in use
OLD_IOS, OLD_ANDROID = 13, 5

DATA = Path(__file__).resolve().parent / "data"


def ip_to_int(ip: Optional[str]) -> int:
    """An IPv4 dotted quad as an integer, or 0 for anything else (IPv6 included; 0 is never inside
    a loaded range)."""
    parts = (ip or "").split(".")
    if len(parts) != 4:
        return 0
    try:
        a, b, c, d = (int(p) for p in parts)
    except ValueError:
        return 0
    return (a << 24) + (b << 16) + (c << 8) + d if all(0 <= x < 256 for x in (a, b, c, d)) else 0


def ref_host(ref: Optional[str]) -> str:
    """The referrer's host in lower case, or "" for none (an empty referrer, or "Unknown")."""
    ref = (ref or "").strip()
    if not ref or ref.lower() == "unknown":
        return ""
    if "://" not in ref:
        ref = "//" + ref  # a bare host with no scheme
    return (urlsplit(ref).hostname or "").lower()


def agent_is_old_phone(agent: Optional[str], old_ios: int = OLD_IOS, old_android: int = OLD_ANDROID) -> bool:
    """A phone agent naming iOS `old_ios` or older, or Android `old_android` or older."""
    agent = agent or ""
    ios, android = IOS_RE.search(agent), ANDROID_RE.search(agent)
    return bool((ios and int(ios.group(1)) <= old_ios) or (android and int(android.group(1)) <= old_android))


class Ranges:
    """Sorted (lo, hi) IPv4 ranges with a binary-search membership test."""

    def __init__(self, ranges: Iterable[tuple[int, int]] = ()):
        pairs = sorted(ranges)
        self.los = [lo for lo, _ in pairs]
        self.his = [hi for _, hi in pairs]

    def __len__(self) -> int:
        return len(self.los)

    def contains(self, value: int) -> bool:
        if value <= 0 or not self.los:
            return False
        i = bisect.bisect_right(self.los, value) - 1
        return 0 <= i < len(self.los) and self.los[i] <= value <= self.his[i]

    @classmethod
    def read(cls, path: Path) -> "Ranges":
        """The "<lo> <hi> [label]" lines of a ranges file; a missing file is no ranges, never a crash."""
        pairs = []
        try:
            for line in Path(path).read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    lo, hi = line.split()[:2]
                    pairs.append((int(lo), int(hi)))
        except FileNotFoundError:
            pass
        return cls(pairs)


def read_hosts(path: Path) -> frozenset:
    """One host per line, lower case, comments starting with #; a missing file is an empty set."""
    try:
        lines = Path(path).read_text().splitlines()
    except FileNotFoundError:
        return frozenset()
    return frozenset(ln.strip().lower() for ln in lines if ln.strip() and not ln.strip().startswith("#"))


class Classifier:
    """The classification, with your own checks' agents and the lists it reads.

    `own_agents` is a regular expression (or a compiled one) that matches the user agents of your
    own checks; None means no agent is yours. `data_dir` is a folder holding refreshed copies of
    `datacenter_nets.txt` and `spam_referrers.txt` (what `realvisits refresh --out` writes); a file
    missing there is read from the copy shipped with the package. The lists are read once, on first
    use, and again after `reload()`."""

    def __init__(self, own_agents: Union[str, Pattern, None] = None, data_dir: Union[str, Path, None] = None,
                 *, old_ios: int = OLD_IOS, old_android: int = OLD_ANDROID):
        self.own_re = re.compile(own_agents, re.I) if isinstance(own_agents, str) else own_agents
        self.data_dir = Path(data_dir) if data_dir else None
        self.old_ios, self.old_android = old_ios, old_android
        self._ranges: Optional[Ranges] = None
        self._spam: Optional[frozenset] = None

    def data_file(self, name: str) -> Path:
        """The refreshed copy in `data_dir` when it is there, else the shipped one."""
        if self.data_dir is not None and (self.data_dir / name).exists():
            return self.data_dir / name
        return DATA / name

    def reload(self) -> None:
        """Read the lists again on next use (after a refresh)."""
        self._ranges = None
        self._spam = None

    @property
    def ranges(self) -> Ranges:
        if self._ranges is None:
            self._ranges = Ranges.read(self.data_file("datacenter_nets.txt"))
        return self._ranges

    @property
    def spam_hosts(self) -> frozenset:
        if self._spam is None:
            self._spam = read_hosts(self.data_file("spam_referrers.txt"))
        return self._spam

    def is_own(self, agent: Optional[str]) -> bool:
        return bool(self.own_re and self.own_re.search(agent or ""))

    def agent_is_bot(self, agent: Optional[str]) -> bool:
        agent = agent or ""
        return (agent == "" or bool(BOT_AGENT_RE.search(agent))
                or agent_is_old_phone(agent, self.old_ios, self.old_android))

    def ip_is_datacenter(self, ip: Optional[str]) -> bool:
        return self.ranges.contains(ip_to_int(ip))

    def ref_is_spam(self, ref: Optional[str]) -> bool:
        host = ref_host(ref)
        return bool(host) and any(host == s or host.endswith("." + s) for s in self.spam_hosts)

    def own_addresses(self, visits: Iterable[tuple]) -> set:
        """The (day, address) pairs your own checks came from, from (day, agent, address) visits:
        every address an own-agent visit used, on the day it used it. `day` is whatever groups
        your visits (a date string, a date)."""
        return {(day, ip) for day, agent, ip in visits if ip and self.is_own(agent)}

    def classify(self, agent: Optional[str], ip: Optional[str], ref: Optional[str],
                 from_own_address: bool = False) -> str:
        """"own", "bot" or "person" for one visit. `from_own_address` says its (day, address) is in
        own_addresses() of that day's visits; classify_visits() works it out for you."""
        if self.is_own(agent) or from_own_address:
            return OWN
        if self.agent_is_bot(agent) or self.ip_is_datacenter(ip) or self.ref_is_spam(ref):
            return BOT
        return PERSON

    def classify_visits(self, visits: Iterable[tuple]) -> list:
        """The class of each (day, agent, address, referrer) visit, in order, with your own
        addresses learned from the same visits."""
        visits = list(visits)
        ours = self.own_addresses((day, agent, ip) for day, agent, ip, _ref in visits)
        return [self.classify(agent, ip, ref, (day, ip) in ours) for day, agent, ip, ref in visits]
