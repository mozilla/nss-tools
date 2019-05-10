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

from utils.types import Patch, PackageVersion, Validator

def info(message):
  print(Fore.GREEN + message)

def log(message):
  print(message)

def get_version(hgclient, *, rev=None, validator) -> PackageVersion:
  if Path("lib/nss/nss.h").exists():
    contents = hgclient.cat([b"lib/nss/nss.h"], rev=rev).decode(encoding="UTF-8")
    return PackageVersion.from_header(component="NSS", header=contents,
                                      validator=validator)
  elif Path("pr/include/prinit.h").exists():
    contents = hgclient.cat([b"pr/include/prinit.h"], rev=rev).decode(encoding="UTF-8")
    return PackageVersion.from_header(component="NSPR", header=contents,
                                      validator=validator)
  raise Exception("No version files found")

def bug_status_check(*, bugdata, patch, validator: Validator):
  if patch.type == 'patch':
    if bugdata.status not in ["NEW", "ASSIGNED", "REOPENED"]:
      validator.warn(f"Bug {bugdata.id} is in an odd state for a patch: {bugdata.status}")
  elif patch.type == 'backout':
    if bugdata.status not in ["RESOLVED"]:
      validator.warn(f"Bug {bugdata.id} is in an odd state for a backout: {bugdata.status}")
  else:
    validator.fatal("Unknown patch type: " + patch.type)

def resolve(*, hgclient, bzapi, patch: Patch, validator: Validator):
  repo = hgclient.paths(name=b'default').decode(encoding='UTF-8').split('@')[1]

  bugdata = bzapi.getbug(patch.bug)

  bug_status_check(bugdata=bugdata, patch=patch, validator=validator)

  if patch.type == "backout":
    comment = f"Backed out for {patch.reason}\n"
  else:
    comment = f"https://{repo}rev/{patch.hash.decode(encoding='UTF-8')}\n"

  version = get_version(hgclient, rev=patch.hash, validator=validator)
  info(f"Patch {patch} is against {version.component} {version.number}")

  info(f"Adding comment to bug {patch.bug}:")

  if patch.type == 'patch':
    log(comment)
    answers = prompt([{'type': 'confirm', 'message': 'Submit this comment and resolve the bug?',
                      'name': 'resolve'}])
    if answers['resolve']:
      update = bzapi.build_update(comment=comment, status="RESOLVED",
                                  resolution="FIXED",
                                  target_milestone=version.number,
                                  keywords_remove="checkin-needed")
      breakpoint()
      bzapi.update_bugs([patch.bug], update)
      info(f"Resolved {bugdata.weburl}")

  elif patch.type == 'backout':
    log(comment)
    answers = prompt([{'type': 'confirm', 'message': 'Submit this comment and reopen the bug?',
                      'name': 'resolve'}])
    if answers['resolve']:
      update = bzapi.build_update(comment=comment, status="REOPENED",
                                  resolution="---",
                                  target_milestone="---")
      breakpoint()
      bzapi.update_bugs([patch.bug], update)
      info(f"Reopened {bugdata.weburl}")

  else:
    validator.fatal(f"Unknown patch type: {patch.type}")

def process_patches(*, hgclient, bzapi, revrange: str, patches: list,
                    validator: Validator):
  bug = None

  version = get_version(hgclient, rev=revrange, validator=validator)
  info(f"Patchset {revrange} is against {version.component} {version.number}")

  if len(patches) != 1:
    raise Exception("One at a time right now")

  for patch in patches:
    if patch.type is 'tag':
      continue

    if bug is None:
      bug = patch.bug
    elif bug != patch.bug:
      validator.fatal(f"Multiple bugs in one revrange: {bug}, {patch.bug}")

    bugdata = bzapi.getbug(patch.bug)

    info(bugdata.__str__())
    log(f"Component: {bugdata.component}")
    log(bugdata.weburl)
    log(bugdata.status)
    log(bugdata.type)
    log(f"Version: {bugdata.version}")
    log(f"Target: {bugdata.target_milestone}")

    if bugdata.component != version.component and bugdata.product != version.component:
      validator.fatal(f"Bug component mismatch. Bug is for {bugdata.product}::{bugdata.component}, but we're in {version.component}")

    if bugdata.target_milestone != version.number:
      validator.warn(f"Bug target milestone ({bugdata.target_milestone}) is not set to {version.number}")

    bug_status_check(bugdata=bugdata, patch=patch, validator=validator)

    answers = prompt([{'type': 'confirm', 'message': 'Push and resolve bug?', 'name': 'push'}])
    if answers['push']:
      log("Now run:")
      info(f"  hg push -r {revrange}")

      if prompt([{'type': 'confirm', 'message': 'Was your push successful?', 'name': 'push'}])['push']:
        resolve(hgclient=hgclient, bzapi=bzapi, patch=patch)

def main():
  init(autoreset=True)

  parser = OptionParser()
  parser.add_option("-b", "--bug",
                    help="bug number to search, used with -l")
  parser.add_option("-l", "--landed",
                    help="as-landed hg revision, used with -b")
  parser.add_option("-r", "--revrange", default=".",
                    help="hg revision range")
  parser.add_option("-s", "--resolve",
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

  validator = Validator()

  info(f"Interacting with Bugzilla at {bzapi.url}. Logged in = {bzapi.logged_in}")

  try:
    if options.bug and options.landed:
      commits = hgclient.log(revrange=options.landed)
      if len(commits) != 1:
        validator.fatal(f"Couldn't find revision {options.landed}")

      patch = Patch(commit=commits[0], validator=validator)
      resolve(hgclient=hgclient, bzapi=bzapi, patch=patch,
              validator=validator)

    elif options.bug or options.landed:
      validator.fatal("You have to specify --bug and --landed together")

    elif options.resolve:
      commits = hgclient.log(revrange=options.resolve)
      if not commits:
        validator.fatal("No changes found")

      if len(commits) != 1:
        raise Exception("Only one at a time now")

      for commit in commits:
        patch = Patch(commit=commit, validator=validator)
        if patch.type is "patch":
          resolve(hgclient=hgclient, bzapi=bzapi, patch=patch,
                  validator=validator)

    else:
      commits = hgclient.outgoing(revrange=options.revrange)
      if not commits:
        validator.fatal("No changes found")

      patches = []
      for commit in commits:
        patches.append(Patch(commit=commit, validator=validator))

      process_patches(hgclient=hgclient, bzapi=bzapi, revrange=options.revrange,
                      patches=patches, validator=validator)

  except hglib.error.CommandError as ce:
    validator.fatal(f"Mercurial error {ce.err.decode(encoding='UTF-8')}")

if __name__ == "__main__":
  main()