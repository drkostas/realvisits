"""realvisits: sort the visits a website records into people, bots and the site's own checks."""
from realvisits.classify import (
    BOT, BOT_AGENT_RE, OWN, PERSON, Classifier, Ranges, agent_is_old_phone, ip_to_int, read_hosts, ref_host,
)

__version__ = "0.1.0"
__all__ = ["BOT", "BOT_AGENT_RE", "OWN", "PERSON", "Classifier", "Ranges", "agent_is_old_phone", "ip_to_int",
           "read_hosts", "ref_host", "__version__"]
