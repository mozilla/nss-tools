import re

from colorama import init, Fore
from dataclasses import dataclass
from whaaaaat import prompt

RE_patch = r'[Bb]ug (?P<bug>[0-9]+)[ ,-]*(?P<desc>.+) +(?P<reviewers>r[?=].*)* *(?P<approvers>a=.*)*'
RE_backout = r'(backout|back.* out|Back.* out|Backout)'
RE_backout_std = r'[Bb]acked out changeset (?P<changeset>[a-z0-9]+).*'
RE_backout_template = r'[Bb]acked out changeset (?P<changeset>[a-z0-9]+) \([Bb]ug (?P<bug>[0-9]+)\) for (?P<reason>.+)'
RE_nss_version = r'#define NSS_VERSION "(?P<version>[0-9.]+)"'
RE_nspr_version = r'#define PR_VERSION +"(?P<version>[0-9.]+).*"'
RE_tag = r'Added tag (?P<tag>[A-Z0-9_]+) for changeset (?P<changeset>[a-z0-9]+)'

@dataclass
class Validator:
  warnings: list
  ask: bool

  def __init__(self, *, ask=True):
    self.warnings = []
    self.ask = ask

  def fatal(self, message):
    print(Fore.RED + "[die] " + message)
    exit()

  def warn(self, message):
    self.warnings.append(message)

    print(Fore.YELLOW + "[WARN] " + message)
    if self.ask:
      answers = prompt([{'type': 'confirm', 'message': 'Proceed anyway?',
                         'name': 'okay'}])
      if not answers['okay']:
        exit()

class NullValidator:
  def __init__(self):
    pass

  def fatal(self, message):
    pass

  def warn(self, message):
    pass

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
  headline: str
  id: str
  hash: str
  author: str
  message: str
  timestamp: str
  bug: int = None
  reviewers: list = None
  tag: str = None
  reason: str = None
  description: str = None

  def __init__(self, *, validator: Validator, commit: list):
    self.headline = commit[5].decode(encoding='UTF-8').split("\n")[0]

    if re.match(RE_backout, self.headline):
      self.__init_backout(validator, commit)
    elif re.match(RE_tag, self.headline):
      self.__init_tag(validator, commit)
    else:
      self.__init_bug(validator, commit)

  def __repr__(self) -> str:
    return f"[{self.type}]: {self.headline}"

  def __init_bug(self, validator: Validator, commit):
    matches = re.match(RE_patch, self.headline)
    if matches:
      self.reviewers = matches.group("reviewers")
      self.bug = matches.group("bug")
      self.description = matches.group("desc")
    else:
      validator.warn(f"Patch headline doesn't parse: {self.headline}")

    self.type = "patch"
    self.id = commit[0]
    self.hash = commit[1]
    self.author = commit[4]
    self.message = commit[5].decode(encoding='UTF-8')
    self.timestamp = commit[6]

  def __init_backout(self, validator: Validator, commit):
    extended_match = re.match(RE_backout_template, self.headline)
    if extended_match:
      self.bug = extended_match.group("bug")
      self.changeset = extended_match.group("changeset")
      self.reason = extended_match.group("reason")
    else:
      validator.warn("Backout headline needs to be of the form: Backed out changeset X (bug Y) for REASON")

      matches = re.match(RE_backout_std, self.headline)
      if matches:
        self.changeset = matches.group("changeset")
      else:
        validator.warn(f"Backout headline doesn't parse: {self.headline}")

    self.type = "backout"
    self.id = commit[0]
    self.hash = commit[1]
    self.author = commit[4]
    self.message = commit[5].decode(encoding='UTF-8')
    self.timestamp = commit[6]

  def __init_tag(self, validator: Validator, commit):
    tagmatches = re.match(RE_tag, self.headline)
    if not tagmatches:
      validator.fatal(f"Tag headline doesn't parse: {self.headline}")

    self.type = "tag"
    self.changeset = tagmatches.group("changeset")
    self.tag = tagmatches.group("tag")
    self.id = commit[0]
    self.hash = commit[1]
    self.author = commit[4]
    self.message = commit[5].decode(encoding='UTF-8')
    self.timestamp = commit[6]

  def validate(self, *, validator: Validator) -> bool:
    if self.type in ["patch", "backout"]:
      if not self.bug:
        validator.warn("No bug number found")
        return False

    if self.type is "backout":
      if not self.changeset or not self.reason:
        validator.warn("No changeset or reason in backout")
        return False

    if self.type is "patch":
      if not self.reviewers:
        validator.warn("No reviewers found")

    return True

  def verify_tag_version(self, *, validator: Validator, version: PackageVersion):
    expected_version = version.number.replace(".", "_")
    if not expected_version in tag:
      validator.fatal(f"Tag {tag} doesn't contain {expected_version}")

    validator.info(f"Tag {tag} for version {version.number} detected. Format looks good.")

