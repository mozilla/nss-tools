import re

from colorama import init, Fore
from dataclasses import dataclass
from whaaaaat import prompt

RE_bugnum = r'[Bb]ug (?P<bug>[0-9]+)'
RE_reviewers = r' (?P<reviewers>r[?=].*)+'
RE_backout = r'(backout|back.* out|Back.* out|Backout)'
RE_backout_template = r'[Bb]acked out changeset (?P<changeset>[a-z0-9]+) \([Bb]ug (?P<bug>[0-9]+)\) for (?P<reason>.+)'
RE_nss_version = r'#define NSS_VERSION "(?P<version>[0-9.]+)"'
RE_nspr_version = r'#define PR_VERSION +"(?P<version>[0-9.]+).*"'
RE_tag = r'Added tag (?P<tag>[A-Z0-9_]+) for changeset (?P<changeset>[a-z0-9]+)'

@dataclass
class Validator:
  warnings: list

  def __init__(self):
    self.warnings = []

  def fatal(self, message):
    print(Fore.RED + "[die] " + message)
    exit()

  def warn(self, message):
    self.warnings.append(message)

    print(Fore.YELLOW + "[WARN] " + message)
    answers = prompt([{'type': 'confirm', 'message': 'Proceed anyway?',
                       'name': 'okay'}])
    if not answers['okay']:
      exit()


@dataclass
class PackageVersion:
  component: str
  number: str

  @staticmethod
  def extract_version(contents: str, *, regex, validator: Validator) -> str:
      versionmatch = re.search(regex, contents)
      if not versionmatch:
        validator.fatal("Unknown version")
      return versionmatch.group("version")

  @staticmethod
  def from_header(validator: Validator, component: str, header: str):
    if component is "NSS":
      return PackageVersion("NSS", PackageVersion.extract_version(header,
                              regex=RE_nss_version, validator=validator))
    if component is "NSPR":
      return PackageVersion("NSPR", PackageVersion.extract_version(header,
                              regex=RE_nspr_version, validator=validator))
    raise Exception("Unknown component")

@dataclass
class Patch:
  type: str
  bug: int
  reviewers: list
  headline: str
  id: str
  hash: str
  tag: str
  author: str
  reason: str
  message: str
  timestamp: str

  def __init__(self, *, validator: Validator, commit: list):
    self.headline = commit[5].decode(encoding='UTF-8').split("\n")[0]

    if re.match(RE_backout, self.headline):
      self.__init_backout(validator, commit)
    elif re.match(RE_tag, self.headline):
      self.__init_tag(validator, commit)
    else:
      self.__init_bug(validator, commit)

    print(f"Headline: {self.headline}")

  def __repr__(self) -> str:
    return f"[{self.type}] {self.bug}: {self.message}"

  def __init_bug(self, validator: Validator, commit):
    self.type = "patch"

    self.reviewers = self.find_reviewers()
    if not self.reviewers:
      validator.warn("No reviewers found in the headline")

    self.bug = self.find_bug()
    if not self.bug:
      validator.fatal("No bug number found in the headline")

    self.id = commit[0]
    self.hash = commit[1]
    self.author = commit[4]
    self.message = commit[5].decode(encoding='UTF-8')
    self.timestamp = commit[6]

  def __init_backout(self, validator: Validator, commit):
    backoutmatches = re.match(RE_backout_template, self.headline)
    if not backoutmatches:
      validator.fatal("Backout headline needs to be of the form: Backed out changeset X (bug Y) for REASON")

    info("Backout detected. Format looks good.")
    self.type = "backout",
    self.bug = backoutmatches.group("bug")
    self.changeset = backoutmatches.group("changeset")
    self.reason = backoutmatches.group("reason")
    self.id = commit[0]
    self.hash = commit[1]
    self.author = commit[4]
    self.message = commit[5].decode(encoding='UTF-8')
    self.timestamp = commit[6]

  def __init_tag(self, validator: Validator, commit):
    tagmatches = re.match(RE_tag, self.headline)
    if not tagmatches:
      validator.fatal("Tag headline isn't formatted as expected")

    self.type = "tag",
    self.changeset = tagmatches.group("changeset")
    self.tag = tagmatches.group("tag")
    self.id = commit[0]
    self.hash = commit[1]
    self.author = commit[4]
    self.message = commit[5].decode(encoding='UTF-8')
    self.timestamp = commit[6]

  def find_reviewers(self):
    reviewermatches = re.search(RE_reviewers, self.headline)
    if not reviewermatches:
      return []
    return reviewermatches.group("reviewers")

  def find_bug(self):
    bugmatches = re.match(RE_bugnum, self.headline)
    if not bugmatches:
      return None
    return bugmatches.group("bug")

  def verify_tag_version(self, *, validator: Validator, version: PackageVersion):
    expected_version = version.number.replace(".", "_")
    if not expected_version in tag:
      validator.fatal(f"Tag {tag} doesn't contain {expected_version}")

    validator.info(f"Tag {tag} for version {version.number} detected. Format looks good.")

