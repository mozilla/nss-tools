#!/usr/local/bin/python3

import bugzilla
import hglib
import io, os, json
import pyperclip
from colorama import init, Fore
from optparse import OptionParser
from pathlib import Path

from utils.types import Patch, PackageVersion, Validator

# todo: dedupe with nss-land-commit
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

def main():
  init(autoreset=True)

  parser = OptionParser()
  parser.add_option("-r", "--revrange", default="reverse(ancestors(.))",
                    help="hg revision range like `startHash::.`")
  parser.add_option("--html", action="store_true",
                    help="Provide HTML suitable for the release notes")

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

  print(f"Interacting with Bugzilla at {bzapi.url}. Logged in = {bzapi.logged_in}")

  bugs={}

  commits = hgclient.log(revrange=options.revrange)
  for commit in commits:
    patch = Patch(commit=commit, validator=validator)
    print(f"{patch}")

    version = get_version(hgclient, rev=patch.hash, validator=validator)

    if patch.type is "tag" or patch.bug is None:
      continue

    bugdata = bzapi.getbug(patch.bug)

    if bugdata.product == "NSS":
      if bugdata.target_milestone != version.number:
        validator.warn(f"Version mismatch! target_milestone set to {bugdata.target_milestone} but hg says {version.number}")

    else:
      validator.warn(f"Bug {patch.bug} is not for NSS ({bugdata.product}). Odd. Skipping.")
      continue

    if bugdata.status not in ["RESOLVED"]:
      validator.warn(f"Status is not resolved! bug set to {bugdata.status}. Skipping.")
      continue

    bugs[bugdata.id] = bugdata

  if options.html:
    with io.StringIO() as buf:
      print("<ul>", file=buf)
      for bugid, bugdata in bugs.items():
        print(f'  <li><a href="{bugdata.weburl}">{bugid}</a> - {bugdata.summary}</li>', file=buf)
      print("</ul>", file=buf)

      print("\n\n")
      print(buf.getvalue())

      pyperclip.copy(buf.getvalue())
      print("(Copied to clipboard)")

if __name__ == "__main__":
  main()