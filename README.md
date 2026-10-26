# realvisits

Sort the visits a website records into people, bots and the site's own checks.

A self-hosted visit counter keeps a user agent, an address and a referrer for each visit, and most of those visits are not people. Crawlers and scripts say so in their user agent, but scrapers send a copied browser agent from a cloud server, referrer spam arrives from real-looking browsers, and your own uptime checks and test runs visit more than anyone. realvisits answers `own`, `bot` or `person` for each visit from what the counter already stored. It is meant to run when you read the visits, not when you store them, so a better list re-reads your whole history without rewriting a row.

Standard library only, Python 3.9 or newer.

```bash
pip install git+https://github.com/drkostas/realvisits
```

## Use

```python
from realvisits import Classifier

c = Classifier(own_agents=r"^uptime-probe/|\(deploy check\)")

c.classify(agent, ip, referrer)            # "own", "bot" or "person" for one visit

# a day's (or any period's) visits as (day, agent, ip, referrer), with your own address learned
labels = c.classify_visits(visits)
```

On the command line, `check` classifies one visit.

```bash
realvisits check "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ..." 203.0.113.7 https://example.org/
```

## How a visit is classified

In this order, and the first rule that matches decides.

1. **Own.** Its user agent matches `own_agents`, the pattern of your own checks. Or it came from an address one of those checks used the same day. Your uptime checks usually run from the machine your tests and your own browser run on, so the address they came from on a day is that machine's address that day. A test run there that sends an ordinary agent is then yours too (Playwright's "Desktop Chrome" device sends a Windows agent with no referrer, which looks like a person). The address is learned from the visits, per day, so there is nothing to configure and nothing to update when it changes. `classify_visits` does this for you, and `own_addresses` gives the pairs on their own.
2. **Bot.** Any of these.
   - The user agent names a crawler, a script, an HTTP library, a headless browser or a monitor, or it is empty.
   - The user agent is a phone too old to be in use, iOS 13 or older or Android 5 or older (`old_ios` and `old_android` change that). "iPhone OS 13_2_3" is Chrome DevTools' default iPhone emulation. Desktop versions say nothing, because every current Mac browser sends "Mac OS X 10_15_7" and every Windows one "Windows NT 10.0", and Chrome on Android sends "Android 10; K" whatever the phone runs.
   - The address is in a cloud or hosting network (`data/datacenter_nets.txt`).
   - The referrer's host, or a domain above it, is a known referrer-spam host (`data/spam_referrers.txt`).
3. **Person.** Everything else. A visit with no referrer is still a person, since people type addresses and single-page apps keep the first referrer for every page.

The cloud ranges come from a curated list of cloud and hosting ASNs (`data/datacenter_asns.txt`, 62 ASNs of AWS, Google Cloud, Azure, Hetzner, OVH and other providers). CDN and consumer-VPN networks that put real people behind their addresses, such as Cloudflare, are left out on purpose, so a visitor behind one still counts as a person.

## Keeping the lists current

The package ships with a copy of both lists. To refresh them, run this on a schedule (weekly is plenty) and point the classifier at the folder.

```bash
realvisits refresh --out /path/to/data --spam
```

```python
c = Classifier(own_agents=..., data_dir="/path/to/data")   # c.reload() after a refresh
```

`refresh` downloads the public [ip2asn](https://iptoasn.com/) IPv4 dataset and keeps every range whose ASN is in the policy. With `--spam` it also merges [Matomo's referrer-spam list](https://github.com/matomo-org/referrer-spam-list) into your copy. `--asns my_asns.txt` uses your own policy (copy the shipped one and add a provider), and `--ip2asn file.tsv` reads a local copy of the dataset instead of downloading it. A list missing from `data_dir` is read from the shipped copy.

## Two signals it does not use

Both were measured on two months of a small set of personal sites, and both would count real people as bots.

- **No referrer together with no reverse DNS.** More than half of the real visitors with no referrer came from addresses with no reverse DNS, mostly mobile networks. It would also need a DNS lookup for every address at read time, and DNS changes, so old days would read differently each time.
- **Many hits from one user agent on a few addresses.** The only case in those two months was the sites' own test runs, which the own-address rule already catches, while a real session in a single-page app also sends many hits with no referrer.

## Tests

```bash
python -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

The tests use addresses from the documentation ranges (RFC 5737) and stand-in lists, and read the network nowhere.

## License

MIT
