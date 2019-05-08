#!/usr/local/bin/python3

import io, os, re
import bugzilla
import requests
import json
import hglib
from colorama import init, Fore
from dataclasses import dataclass
from optparse import OptionParser
from pathlib import Path
from whaaaaat import prompt

RE_bugnum = r'[Bb]ug (?P<bug>[0-9]+)'
RE_reviewers = r' (?P<reviewers>r[?=].*)+'
RE_backout = r'(backout|back.* out|Back.* out|Backout)'
RE_backout_template = r'[Bb]acked out changeset (?P<changeset>[a-z0-9]+) \([Bb]ug (?P<bug>[0-9]+)\) for (?P<reason>.+)'
RE_nss_version = r'#define NSS_VERSION "(?P<version>[0-9.]+)"'
RE_nspr_version = r'#define PR_VERSION +"(?P<version>[0-9.]+).*"'
RE_tag = r'Added tag (?P<tag>[A-Z0-9_]+) for changeset (?P<changeset>[a-z0-9]+)'

def fatal(message):
  print(Fore.RED + "[die] " + message)
  exit()

def warn(message):
  print(Fore.YELLOW + "[WARN] " + message)
  answers = prompt([{'type': 'confirm', 'message': 'Proceed anyway?',
                    'name': 'okay'}])
  if not answers['okay']:
    exit()

def info(message):
  print(Fore.GREEN + message)

def log(message):
  print(message)

def extract_version(contents: str, *, regex=None) -> str:
    versionmatch = re.search(regex, contents)
    if not versionmatch:
      fatal("Unknown version")
    return versionmatch.group("version")

@dataclass
class PackageVersion:
  component: str
  number: str

def get_version(hgclient, *, rev=None) -> PackageVersion:
  if Path("lib/nss/nss.h").exists():
    header_file = hgclient.cat([b"lib/nss/nss.h"], rev=rev).decode(encoding="UTF-8")
    return PackageVersion("NSS", extract_version(header_file, regex=RE_nss_version))
  elif Path("pr/include/prinit.h").exists():
    header_file = hgclient.cat([b"pr/include/prinit.h"], rev=rev).decode(encoding="UTF-8")
    return PackageVersion("NSPR", extract_version(header_file, regex=RE_nspr_version))
  raise Exception("No version files found")

def process_bug(commit, headline: str, *, bug: int=None):
  log(f"Headline: {headline}")

  reviewers = []
  reviewermatches = re.search(RE_reviewers, headline)
  if not reviewermatches:
    warn("No reviewers found in the headline")
  else:
    reviewers = reviewermatches.group("reviewers")

  bugmatches = re.match(RE_bugnum, headline)
  if not bugmatches and not bug:
    fatal("No bug number found in the headline and none provided")
  elif bugmatches and not bug:
    if bug is not None and bug != bugmatches.group("bug"):
      warn(f"Bug number {bug} was provided, but using {bugmatches.group('bug')} from the headline")
    bug = bugmatches.group("bug")

  return {
    'type': "patch",
    'bug': bug,
    'reviewers': reviewers,
    'headline': headline,
    'id': commit[0],
    'hash': commit[1],
    'author': commit[4],
    'message': commit[5].decode(encoding='UTF-8'),
    'timestamp': commit[6],
  }

def process_backout(commit, headline: str):
  log("Headline: " + headline)

  backoutmatches = re.match(RE_backout_template, headline)
  if not backoutmatches:
    fatal("Backout headline needs to be of the form: Backed out changeset X (bug Y) for REASON")

  info("Backout detected. Format looks good.")
  return {
    'type': "backout",
    'bug': backoutmatches.group("bug"),
    'changeset': backoutmatches.group("changeset"),
    'reason': backoutmatches.group("reason"),
    'headline': headline,
    'id': commit[0],
    'hash': commit[1],
    'author': commit[4],
    'message': commit[5].decode(encoding='UTF-8'),
    'timestamp': commit[6],
  }

def process_tag(commit, headline: str, *, version: PackageVersion):
  tagmatches = re.match(RE_tag, headline)
  if not tagmatches:
    fatal("Tag headline isn't formatted as expected")

  expected_version = version.number.replace(".", "_")
  tag = tagmatches.group("tag")

  if not expected_version in tag:
    fatal(f"Tag {tag} doesn't contain {expected_version}")

  info(f"Tag {tag} for version {version.number} detected. Format looks good.")

  return {
    'type': "tag",
    'changeset': tagmatches.group("changeset"),
    'headline': headline,
    'tag': tag,
    'version': version,
    'id': commit[0],
    'hash': commit[1],
    'author': commit[4],
    'message': commit[5].decode(encoding='UTF-8'),
    'timestamp': commit[6],
  }

def bug_status_check(*, bugdata, patch):
  if patch['type'] == 'patch':
    if bugdata.status not in ["NEW", "ASSIGNED", "REOPENED"]:
      warn(f"Bug {bugdata.id} is in an odd state for a patch: {bugdata.status}")
  elif patch['type'] == 'backout':
    if bugdata.status not in ["RESOLVED"]:
      warn(f"Bug {bugdata.id} is in an odd state for a backout: {bugdata.status}")
  else:
    fatal("Unknown patch type: " + patch['type'])

def resolve(*, hgclient, bzapi, version: PackageVersion, bug: int, commits):
  repo = hgclient.paths(name=b'default').decode(encoding='UTF-8').split('@')[1]

  bugdata = bzapi.getbug(bug)

  patch_type = None
  comment = ""
  for patch in collect_patches(version=version, commits=commits, expected_bug=bug):
    if patch_type == None:
      patch_type = patch['type']
    elif patch_type != patch['type']:
      warn(f"Some of the patches are of different types: {patch_type}, {patch['type']}")

    if patch['bug'] != bug:
      warn(f"Patch bug number {patch['bug']} doesn't match expected {bug}.")

    if patch_type == "backout" and comment == "":
      comment += f"Backed out for {patch['reason']}\n"

    bug_status_check(bugdata=bugdata, patch=patch)

    comment += f"https://{repo}rev/{patch['hash'].decode(encoding='UTF-8')}\n"

  info(f"Adding comment to bug {bug}:")

  if patch_type == 'patch':
    log(comment)
    answers = prompt([{'type': 'confirm', 'message': 'Submit this comment and resolve the bug?',
                      'name': 'resolve'}])
    if answers['resolve']:
      update = bzapi.build_update(comment=comment, status="RESOLVED",
                                  resolution="FIXED",
                                  target_milestone=version.number,
                                  keywords_remove="checkin-needed")
      breakpoint()
      bzapi.update_bugs([bug], update)
      info(f"Resolved {bugdata.weburl}")

  elif patch_type == 'backout':
    log(comment)
    answers = prompt([{'type': 'confirm', 'message': 'Submit this comment and reopen the bug?',
                      'name': 'resolve'}])
    if answers['resolve']:
      update = bzapi.build_update(comment=comment, status="REOPENED",
                                  resolution="---",
                                  target_milestone="---")
      breakpoint()
      bzapi.update_bugs([bug], update)
      info(f"Reopened {bugdata.weburl}")

  else:
    fatal(f"Unknown patch type: {patch_type}")

def collect_patches(*, version: PackageVersion, commits, expected_bug=None):
  patches=[]
  for commit in commits:
    headline = commit[5].decode(encoding='UTF-8').split("\n")[0]

    if re.match(RE_backout, headline):
      patches.append(process_backout(commit, headline))
    elif re.match(RE_tag, headline):
      patches.append(process_tag(commit, headline, version=version))
    else:
      patches.append(process_bug(commit, headline, bug=expected_bug))

  return patches

def process_patches(*, hgclient, bzapi, version: PackageVersion, revrange: str, patches, commits):
  bug = None

  for patch in patches:
    if patch['type'] == 'tag':
      continue

    if bug is None:
      bug = patch['bug']
    elif bug != patch['bug']:
      fatal(f"Multiple bugs in one revrange: {bug}, {patch['bug']}")

    bugdata = bzapi.getbug(patch['bug'])

    info(bugdata.__str__())
    log(f"Component: {bugdata.component}")
    log(bugdata.weburl)
    log(bugdata.status)
    log(bugdata.type)
    log(f"Version: {bugdata.version}")
    log(f"Target: {bugdata.target_milestone}")

    if bugdata.component != version.component and bugdata.product != version.component:
      fatal(f"Bug component mismatch. Bug is for {bugdata.product}::{bugdata.component}, but we're in {version.component}")

    if bugdata.target_milestone != version.number:
      warn(f"Bug target milestone ({bugdata.target_milestone}) is not set to {version.number}")

    bug_status_check(bugdata=bugdata, patch=patch)

    answers = prompt([{'type': 'confirm', 'message': 'Push and resolve bug?', 'name': 'push'}])
    if answers['push']:
      log("Now run:")
      info(f"  hg push -r {revrange}")

      if prompt([{'type': 'confirm', 'message': 'Was your push successful?', 'name': 'push'}])['push']:
        resolve(hgclient=hgclient, bzapi=bzapi, bug=bug, version=version,
                commits=commits)

def main():
  init(autoreset=True)

  parser = OptionParser()
  parser.add_option("-b", "--bug",
                    help="bug number to search, used with -l")
  parser.add_option("-l", "--landed",
                    help="as-landed hg revision, used with -b")
  parser.add_option("-r", "--revrange", default=".",
                    help="hg revision range")
  parser.add_option("-s", "--resolve", default=".",
                    help="resolve bugs for a given revision range")

  (options, args) = parser.parse_args()

  hgclient = hglib.open(".")

  config = {}
  confFile = Path.home() / ".nss-land-commit.json"
  if confFile.exists():
    with open(confFile, 'r') as conf:
      config = json.load(conf)

  if 'api_key' not in config:
    print(Fore.YELLOW + "Note: Not logging into Bugzilla. BZ actions won't work. Make a file at ~/.nss-land-commit.json")
    print(Fore.YELLOW + "with contents like:")
    log(json.dumps({"api_key": "random_api_key_1e87d00d1c2fb"}))
    bzapi = bugzilla.Bugzilla("bugzilla.mozilla.org")
  else:
    bzapi = bugzilla.Bugzilla("bugzilla.mozilla.org", api_key=config['api_key'])

  info(f"Interacting with Bugzilla at {bzapi.url}. Logged in = {bzapi.logged_in}")

  version = get_version(hgclient)
  info(f"Landing into {version.component} {version.number}")

  try:
    if options.bug and options.landed:
      commits = hgclient.log(revrange=options.landed)
      if len(commits) != 1:
        fatal(f"Couldn't find revision {options.landed}")
      resolve(hgclient=hgclient, bzapi=bzapi, bug=options.bug, commits=commits,
              version=version)

    elif options.bug or options.landed:
      fatal("You have to specify --bug and --landed together")

    elif options.resolve:
      commits = hgclient.log(revrange=options.resolve)
      if not commits:
        fatal("No changes found")

      for patch in collect_patches(version=version, commits=commits):
        if patch['type'] is "patch":
          resolve(hgclient=hgclient, bzapi=bzapi, bug=patch['bug'],
                  commits=commits, version=version)


    else:
      commits = hgclient.outgoing(revrange=options.revrange)
      if not commits:
        fatal("No changes found")

      patches = collect_patches(version=version, commits=commits, bug=options.bug)
      process_patches(hgclient=hgclient, bzapi=bzapi, revrange=options.revrange,
                      patches=patches, version=version, commits=commits)

  except hglib.error.CommandError as ce:
    fatal(f"Mercurial error {ce.err.decode(encoding='UTF-8')}")

if __name__ == "__main__":
  main()