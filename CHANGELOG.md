# Changelog

## 0.1.0

- `Classifier(own_agents=, data_dir=, old_ios=, old_android=)` sorts a visit into `own`, `bot` or `person` from its user agent, address and referrer (`classify`), and a period's visits at once with your own address learned from them (`classify_visits`, `own_addresses`)
- A visit from an address your own checks used that same day is yours, learned per day from the visits
- A bot is a crawler or script by its user agent, an empty agent, a phone on iOS 13 or older or Android 5 or older, an address in a cloud or hosting network, or a referrer-spam host. Frozen desktop versions (Mac OS X 10_15_7, Windows NT 10.0) and Chrome's reduced Android agent stay people
- Shipped lists of cloud and hosting ranges (from 62 curated ASNs) and of referrer-spam hosts, and `realvisits refresh` to rebuild them from the public ip2asn dataset and Matomo's spam list
- `realvisits check` classifies one visit on the command line
