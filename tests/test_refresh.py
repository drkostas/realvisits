import gzip

from realvisits import Classifier, ip_to_int
from realvisits import refresh

# a stand-in ip2asn-v4 dataset: start, end, ASN, country, name (tab separated), with invented ranges
TSV = "\n".join([
    "192.0.2.0\t192.0.2.127\t64500\tZZ\tEXAMPLE-CLOUD",
    "192.0.2.128\t192.0.2.255\t64500\tZZ\tEXAMPLE-CLOUD",     # touches the one above: joined
    "198.51.100.0\t198.51.100.255\t64501\tZZ\tEXAMPLE-ISP",   # not in the policy: left out
    "203.0.113.0\t203.0.113.63\t64502\tZZ\tEXAMPLE-HOST",
    "",
])
POLICY = "# a policy\n64500 ExampleCloud\n64502 ExampleHost\n"


def test_build_ranges_keeps_the_policy_and_joins_touching_ranges():
    merged = refresh.build_ranges(TSV.splitlines(), {"64500": "ExampleCloud", "64502": "ExampleHost"})
    assert merged == [(ip_to_int("192.0.2.0"), ip_to_int("192.0.2.255"), "ExampleCloud"),
                      (ip_to_int("203.0.113.0"), ip_to_int("203.0.113.63"), "ExampleHost")]


def test_run_writes_a_list_the_classifier_reads(tmp_path):
    (tmp_path / "asns.txt").write_text(POLICY)
    (tmp_path / "ip2asn.tsv").write_text(TSV)
    said = []
    out = tmp_path / "data"
    assert refresh.run(out, tmp_path / "asns.txt", str(tmp_path / "ip2asn.tsv"), say=lambda *a, **k: said.append(a[0])) == 0
    c = Classifier(data_dir=out)
    assert c.ip_is_datacenter("192.0.2.200") and c.ip_is_datacenter("203.0.113.10")
    assert not c.ip_is_datacenter("198.51.100.5") and not c.ip_is_datacenter("203.0.113.64")
    assert "2 ASNs, 2 ranges" in said[0]


def test_run_downloads_the_dataset_when_no_file_is_given(tmp_path):
    (tmp_path / "asns.txt").write_text(POLICY)
    asked = []

    def get(url, timeout=120):
        asked.append(url)
        return gzip.compress(TSV.encode())
    assert refresh.run(tmp_path / "data", tmp_path / "asns.txt", get=get, say=lambda *a, **k: None) == 0
    assert asked == [refresh.IP2ASN_URL]


def test_no_ranges_is_a_failure(tmp_path):
    (tmp_path / "asns.txt").write_text("64999 Nobody\n")
    (tmp_path / "ip2asn.tsv").write_text(TSV)
    assert refresh.run(tmp_path / "data", tmp_path / "asns.txt", str(tmp_path / "ip2asn.tsv"), say=lambda *a, **k: None) == 1
    assert not (tmp_path / "data" / "datacenter_nets.txt").exists()


def test_merge_spam_keeps_the_header_and_the_hosts_already_there(tmp_path):
    seed = tmp_path / "seed.txt"
    seed.write_text("# header\n\nold.example\n")
    dest = tmp_path / "spam_referrers.txt"
    n = refresh.merge_spam(dest, seed, get=lambda url, timeout=60: b"new.example\n# a comment\nOLD.example\n")
    assert n == 2
    assert dest.read_text() == "# header\n\nnew.example\nold.example\n"


def test_a_failed_spam_fetch_leaves_the_shipped_list(tmp_path):
    (tmp_path / "asns.txt").write_text(POLICY)
    (tmp_path / "ip2asn.tsv").write_text(TSV)

    def get(url, timeout=60):
        raise OSError("no network")
    said = []
    out = tmp_path / "data"
    assert refresh.run(out, tmp_path / "asns.txt", str(tmp_path / "ip2asn.tsv"), spam=True, get=get,
                       say=lambda *a, **k: said.append(a[0])) == 0
    assert any("spam list refresh skipped" in s for s in said)
    assert "semalt.com" in (out / "spam_referrers.txt").read_text()
