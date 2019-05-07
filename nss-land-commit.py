#!/usr/local/bin/python3

from whaaaaat import prompt
import io, os, re
import bugzilla
import requests
import json
import hglib
from colorama import init, Fore
from optparse import OptionParser

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

def extract_version(contents, *, regex=None):
    versionmatch = re.search(regex, contents)
    if not versionmatch:
      fatal("Unknown version")
    return versionmatch.group("version")

def get_version(hgclient, *, rev=None):
  if os.path.isfile("lib/nss/nss.h"):
    header_file = hgclient.cat([b"lib/nss/nss.h"], rev=rev).decode(encoding="UTF-8")
    return {"component": "NSS", "number": extract_version(header_file, regex=RE_nss_version)}
  elif os.path.isfile("pr/include/prinit.h"):
    header_file = hgclient.cat([b"pr/include/prinit.h"], rev=rev).decode(encoding="UTF-8")
    return {"component": "NSPR", "number": extract_version(header_file, regex=RE_nspr_version)}
  raise Exception("No version files found")

def process_bug(commit, headline, *, bug):
  log("Headline: " + headline)

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
      warn("Bug number {} was provided, but using {} from the headline".format(bug, bugmatches.group("bug")))
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

def process_backout(commit, headline):
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

def process_tag(commit, headline, *, version):
  tagmatches = re.match(RE_tag, headline)
  if not tagmatches:
    fatal("Tag headline isn't formatted as expected")

  expected_version = version['number'].replace(".", "_")
  tag = tagmatches.group("tag")

  if not expected_version in tag:
    fatal("Tag {} doesn't contain {}".format(tag, expected_version))

  info("Tag {} for version {} detected. Format looks good.".format(tag, version['number']))

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
      warn("Bug {} is in an odd state for a patch: {}".format(bugdata.id, bugdata.status))
  elif patch['type'] == 'backout':
    if bugdata.status not in ["RESOLVED"]:
      warn("Bug {} is in an odd state for a backout: {}".format(bugdata.id, bugdata.status))
  else:
    fatal("Unknown patch type: " + patch['type'])

def resolve(*, hgclient, bzapi, version, bug, commits):
  repo = hgclient.paths(name=b'default').decode(encoding='UTF-8').split('@')[1]

  bugdata = bzapi.getbug(bug)

  comment = ""
  for patch in collect_patches(version=version, commits=commits, bug=bug):
    bug_status_check(bugdata=bugdata, patch=patch)

    comment += "https://{}rev/{}\n".format(repo, patch['hash'].decode(encoding='UTF-8'))

  info("Adding comment to bug {}:".format(bug))

  if patch['type'] == 'patch':
    log(comment)
    answers = prompt([{'type': 'confirm', 'message': 'Submit this comment and resolve the bug?',
                      'name': 'resolve'}])
    if answers['resolve']:
      update = bzapi.build_update(comment=comment, status="RESOLVED",
                                  resolution="FIXED",
                                  target_milestone=version['number'],
                                  keywords_remove="checkin-needed")
      breakpoint()
      bzapi.update_bugs([bug], update)
      info("Resolved {}".format(bugdata.weburl))

  elif patch['type'] == 'backout':
    comment = "Backed out for {}\n{}".format(patch['reason'], comment)
    log(comment)
    answers = prompt([{'type': 'confirm', 'message': 'Submit this comment and reopen the bug?',
                      'name': 'resolve'}])
    if answers['resolve']:
      update = bzapi.build_update(comment=comment, status="REOPENED",
                                  resolution="---",
                                  target_milestone="---")
      breakpoint()
      bzapi.update_bugs([bug], update)
      info("Reopened {}".format(bugdata.weburl))

  else:
    fatal("Unknown patch type: " + patch['type'])

def collect_patches(*, version, commits, bug):
  patches=[]
  for commit in commits:
    headline = commit[5].decode(encoding='UTF-8').split("\n")[0]

    if re.match(RE_backout, headline):
      patches.append(process_backout(commit, headline))
    elif re.match(RE_tag, headline):
      patches.append(process_tag(commit, headline, version=version))
    else:
      patches.append(process_bug(commit, headline, bug=bug))

  return patches

def process_patches(*, hgclient, bzapi, version, revrange, patches, commits):
  bug = None

  for patch in patches:
    if patch['type'] == 'tag':
      continue

    if bug is None:
      bug = patch['bug']
    elif bug != patch['bug']:
      fatal("Multiple bugs in one revrange: {}, {}".format(bug, patch['bug']))

    bugdata = bzapi.getbug(patch['bug'])

    info(bugdata.__str__())
    log("Component: {}".format(bugdata.component))
    log(bugdata.weburl)
    log(bugdata.status)
    log(bugdata.type)
    log("Version: {}".format(bugdata.version))
    log("Target: {}".format(bugdata.target_milestone))

    if bugdata.component != version['component'] and bugdata.product != version['component']:
      fatal("Bug component mismatch. Bug is for {}, but we're in {}".format(bugdata.component, version['component']))

    if bugdata.target_milestone != version['number']:
      warn("Bug target milestone ({}) is not set to {}".format(bugdata.target_milestone, version['number']))

    bug_status_check(bugdata=bugdata, patch=patch)

    answers = prompt([{'type': 'confirm', 'message': 'Push and resolve bug?', 'name': 'push'}])
    if answers['push']:
      log("Now run:")
      info("  hg push -r {}".format(revrange))

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

  (options, args) = parser.parse_args()

  hgclient = hglib.open(".")

  config = {}
  confFile = os.path.expanduser('~/.nss-land-commit.json')
  if os.path.exists(confFile):
    with open(confFile, 'r') as conf:
      config = json.load(conf)

  if 'api_key' not in config:
    print(Fore.YELLOW + "Note: Not logging into Bugzilla. BZ actions won't work. Make a file at ~/.nss-land-commit.json")
    print(Fore.YELLOW + "with contents like:")
    log(json.dumps({"api_key": "random_api_key_1e87d00d1c2fb"}))
    bzapi = bugzilla.Bugzilla("bugzilla.mozilla.org")
  else:
    bzapi = bugzilla.Bugzilla("bugzilla.mozilla.org", api_key=config['api_key'])

  info("Interacting with Bugzilla at {}. Logged in = {}".format(bzapi.url, bzapi.logged_in))

  version = get_version(hgclient)
  info("Landing into {component} {number}".format(**version))

  try:
    if options.bug and options.landed:
      commits = hgclient.log(revrange=options.landed)
      if len(commits) != 1:
        fatal("Couldn't find revision {}".format(rev))
      resolve(hgclient=hgclient, bzapi=bzapi, bug=options.bug, commits=commits,
              version=version)

    elif options.bug or options.landed:
      fatal("You have to specify --bug and --landed together")

    else:
      commits = hgclient.outgoing(revrange=options.revrange)
      if not commits:
        fatal("No changes found")

      patches = collect_patches(version=version, commits=commits, bug=options.bug)
      process_patches(hgclient=hgclient, bzapi=bzapi, revrange=options.revrange,
                      patches=patches, version=version, commits=commits)

  except hglib.error.CommandError as ce:
    fatal("Mercurial error {}".format(ce.err.decode(encoding='UTF-8')))

if __name__ == "__main__":
  main()