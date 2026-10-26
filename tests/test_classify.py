import re

import pytest

from realvisits import BOT, OWN, PERSON, Classifier, agent_is_old_phone, ip_to_int, ref_host
from realvisits.cli import main

# A plain desktop browser agent, caught by none of the bot keywords. Windows NT 10.0 is what every
# current Windows browser sends.
BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
# Playwright's "Desktop Chrome" device sends a Windows agent like this one
PLAYWRIGHT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/151.0.7922.34 Safari/537.36")
OWN_CHECKS = r"^uptime-probe/|\(deploy check\)"
HOME = "203.0.113.7"       # a person's address (RFC 5737), in no cloud range
CLOUD = "198.51.100.40"    # inside the stand-in cloud range below


@pytest.fixture
def lists(tmp_path):
    lo, hi = ip_to_int("198.51.100.0"), ip_to_int("198.51.100.255")
    (tmp_path / "datacenter_nets.txt").write_text(f"# stand-in\n{lo} {hi} ExampleCloud\n")
    (tmp_path / "spam_referrers.txt").write_text("# stand-in\nspam.example\n")
    return tmp_path


@pytest.fixture
def c(lists):
    return Classifier(own_agents=OWN_CHECKS, data_dir=lists)


def test_own_checks_by_agent(c):
    assert c.classify("uptime-probe/2 (+https://example.org)", HOME, "") == OWN
    assert c.classify("Mozilla/5.0 (deploy check)", CLOUD, "") == OWN  # own beats a cloud address
    # with no pattern nothing is own: an agent with no bot word is then a person
    assert Classifier().classify("site-probe/2", HOME, "") == PERSON
    assert Classifier(own_agents=r"^site-probe/").classify("site-probe/2", HOME, "") == OWN


@pytest.mark.parametrize("agent", ["curl/8.7.1", "Googlebot/2.1 (+http://www.google.com/bot.html)", "",
                                   None, "python-requests/2.31", "Mozilla/5.0 HeadlessChrome/141.0",
                                   "facebookexternalhit/1.1"])
def test_bot_by_agent(c, agent):
    assert c.classify(agent, HOME, "") == BOT


@pytest.mark.parametrize("agent", [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/13.0.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 12_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 (KHTML, like Gecko) Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 4.4.2; Nexus 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/38 Mobile Safari/537.36",
])
def test_a_phone_too_old_to_be_in_use_is_a_bot(c, agent):
    assert agent_is_old_phone(agent)
    assert c.classify(agent, HOME, "") == BOT


@pytest.mark.parametrize("agent", [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 26_3_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/144.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 6.0.1; SM-J700F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36",
    "Mozilla/5.0 (Android 17; Mobile; rv:158.0) Gecko/158.0 Firefox/158.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    BROWSER,
])
def test_current_devices_and_frozen_desktop_versions_are_people(c, agent):
    assert c.classify(agent, HOME, "") == PERSON


def test_old_phone_thresholds_are_settings(lists):
    agent = "Mozilla/5.0 (Linux; Android 6.0.1; SM-J700F) AppleWebKit/537.36 Mobile Safari/537.36"
    assert Classifier(data_dir=lists, old_android=6).classify(agent, HOME, "") == BOT


def test_bot_by_cloud_address(c):
    assert c.ip_is_datacenter(CLOUD) and not c.ip_is_datacenter(HOME)
    assert c.classify(BROWSER, CLOUD, "https://www.example.org/") == BOT


@pytest.mark.parametrize("ref", ["http://spam.example/", "https://sub.spam.example/x", "spam.example"])
def test_bot_by_referrer_spam(c, ref):
    assert c.classify(BROWSER, HOME, ref) == BOT


def test_spam_is_matched_on_the_host_only(c):
    assert not c.ref_is_spam("https://notspam.example/")
    assert not c.ref_is_spam("https://www.example.org/?from=spam.example")
    assert not c.ref_is_spam("Unknown") and not c.ref_is_spam("") and not c.ref_is_spam(None)


@pytest.mark.parametrize("ref", ["https://www.example.org/", "Unknown", "", "https://github.com/"])
def test_an_ordinary_visit_is_a_person(c, ref):
    assert c.classify(BROWSER, HOME, ref) == PERSON


def test_a_visit_from_an_address_your_checks_used_that_day_is_yours(c):
    # 192.0.2.10 is the machine the checks run from; a Playwright run there sends an ordinary agent
    day, nextday = "2026-01-02", "2026-01-03"
    visits = ([(day, "uptime-probe/2", "192.0.2.10", "")] * 120
              + [(day, PLAYWRIGHT, "192.0.2.10", "Unknown")] * 65
              + [(day, PLAYWRIGHT, HOME, "Unknown")] * 13           # the same agent from a home address
              + [(day, BROWSER, "203.0.113.8", "")]                  # a person who typed the address
              + [(nextday, PLAYWRIGHT, "192.0.2.10", "Unknown")] * 2)  # no check ran from it that day
    assert c.own_addresses((d, a, ip) for d, a, ip, _ in visits) == {(day, "192.0.2.10")}
    got = c.classify_visits(visits)
    assert got.count(OWN) == 185 and got.count(PERSON) == 16 and got.count(BOT) == 0
    assert got[-1] == PERSON  # an address is yours only on the days a check came from it


def test_a_visit_with_no_address_gives_no_address(c):
    assert c.own_addresses([("d", "uptime-probe/2", None), ("d", "uptime-probe/2", "")]) == set()


def test_ip_to_int_and_ref_host():
    assert ip_to_int("1.2.3.4") == (1 << 24) + (2 << 16) + (3 << 8) + 4
    assert ip_to_int("999.1.1.1") == 0 and ip_to_int("2001:db8::1") == 0 and ip_to_int("") == 0
    assert ip_to_int(None) == 0 and ip_to_int("a.b.c.d") == 0
    assert ref_host("https://WWW.Example.org/x") == "www.example.org" and ref_host("example.org") == "example.org"
    assert ref_host("Unknown") == "" and ref_host(None) == ""


def test_missing_lists_are_empty_never_a_crash(tmp_path):
    c = Classifier(data_dir=tmp_path / "nowhere")
    assert c.data_file("datacenter_nets.txt").parent.name == "data"  # falls back to the shipped copy
    empty = Classifier()
    empty.data_file = lambda name: tmp_path / "missing" / name
    assert len(empty.ranges) == 0 and empty.spam_hosts == frozenset()
    assert empty.classify(BROWSER, HOME, "") == PERSON


def test_reload_reads_the_lists_again(c, lists):
    assert not c.ip_is_datacenter(HOME)
    lo = ip_to_int(HOME)
    (lists / "datacenter_nets.txt").write_text(f"{lo} {lo} Example\n")
    assert not c.ip_is_datacenter(HOME)  # cached
    c.reload()
    assert c.ip_is_datacenter(HOME)


def test_the_shipped_lists_load():
    c = Classifier()
    assert len(c.ranges) > 10000
    assert c.ip_is_datacenter("8.8.8.8")  # Google's public resolver, AS15169 in the shipped policy
    assert {"semalt.com", "darodar.com"} <= c.spam_hosts


def test_a_compiled_pattern_works_too(lists):
    assert Classifier(own_agents=re.compile(r"^probe/"), data_dir=lists).classify("probe/1", HOME, "") == OWN


def test_check_on_the_command_line(capsys, lists):
    assert main(["check", "curl/8", HOME]) == 0
    assert capsys.readouterr().out.strip() == BOT
    assert main(["check", BROWSER, CLOUD, "--data", str(lists)]) == 0
    assert capsys.readouterr().out.strip() == BOT
    assert main(["check", "uptime-probe/2", HOME, "--own", OWN_CHECKS]) == 0
    assert capsys.readouterr().out.strip() == OWN
