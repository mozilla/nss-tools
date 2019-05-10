import re

RE_bugnum = r'[Bb]ug (?P<bug>[0-9]+)'
RE_reviewers = r' (?P<reviewers>r[?=].*)+'
RE_backout = r'(backout|back.* out|Back.* out|Backout)'
RE_backout_template = r'[Bb]acked out changeset (?P<changeset>[a-z0-9]+) \([Bb]ug (?P<bug>[0-9]+)\) for (?P<reason>.+)'
RE_nss_version = r'#define NSS_VERSION "(?P<version>[0-9.]+)"'
RE_nspr_version = r'#define PR_VERSION +"(?P<version>[0-9.]+).*"'
RE_tag = r'Added tag (?P<tag>[A-Z0-9_]+) for changeset (?P<changeset>[a-z0-9]+)'