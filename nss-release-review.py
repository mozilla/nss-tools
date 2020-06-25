#!/usr/bin/env python3

import bugzilla
import hglib
import io, os, json
import pyperclip
from colorama import init, Fore
from optparse import OptionParser
from pathlib import Path

from utils.types import Patch, PackageVersion, Validator, NullValidator

# todo: dedupe with nss-land-commit
def get_version(hgclient, *, rev=None, validator) -> PackageVersion:
    if Path("lib/nss/nss.h").exists():
        contents = hgclient.cat([b"lib/nss/nss.h"], rev=rev).decode(encoding="UTF-8")
        return PackageVersion.from_header(
            component="NSS", header=contents, validator=validator
        )
    elif Path("pr/include/prinit.h").exists():
        contents = hgclient.cat([b"pr/include/prinit.h"], rev=rev).decode(
            encoding="UTF-8"
        )
        return PackageVersion.from_header(
            component="NSPR", header=contents, validator=validator
        )
    raise Exception("No version files found")


class ContributorsList:
    def __init__(self):
        self.authors = {}

    def observe(self, author, previousRelease=False):
        if not author in self.authors or previousRelease:
            self.authors[author] = previousRelease

    def list(self, *, limitToNewContributors=True):
        if limitToNewContributors:
            return filter(lambda x: self.authors[x] is False, self.authors)
        return self.authors


def main():
    init(autoreset=True)

    parser = OptionParser()
    parser.add_option(
        "-r",
        "--revrange",
        default="reverse(ancestors(.))",
        help="hg revision range like `reverse(startHash::endHash)`",
    )
    parser.add_option(
        "--html",
        action="store_true",
        help="Provide HTML suitable for the release notes",
    )

    (options, args) = parser.parse_args()

    if "reverse" not in options.revrange:
        print(
            Fore.YELLOW
            + "Warning: You almost certainly want a `reverse` command in your revrange!"
        )

    hgclient = hglib.open(".")

    config = {}
    confFile = Path.home() / ".nss-land-commit.json"
    if confFile.exists():
        with open(confFile, "r") as conf:
            config = json.load(conf)

    if "api_key" not in config:
        print(
            Fore.YELLOW
            + "Note: Not logging into Bugzilla. BZ actions won't work. Make a file at ~/.nss-land-commit.json"
        )
        print(Fore.YELLOW + "with contents like:")
        log(json.dumps({"api_key": "random_api_key_1e87d00d1c2fb"}))
        bzapi = bugzilla.Bugzilla("bugzilla.mozilla.org")
    else:
        bzapi = bugzilla.Bugzilla("bugzilla.mozilla.org", api_key=config["api_key"])

    validator = Validator(ask=False)

    print(f"Interacting with Bugzilla at {bzapi.url}. Logged in = {bzapi.logged_in}")

    bugs = {}
    contribList = ContributorsList()
    contribListLastHash = None

    for commit in hgclient.log(revrange=options.revrange):
        patch = Patch(commit=commit, validator=validator)
        print(f"{patch.hash.decode('utf-8')} - {patch}")

        contribListLastHash = patch.hash

        version = get_version(hgclient, rev=patch.hash, validator=validator)

        if patch.type == "tag" or patch.bug is None:
            continue

        contribList.observe(patch.author.decode("utf-8"), previousRelease=False)

        bugdata = bzapi.getbug(patch.bug)

        if bugdata.product == "NSS":
            if bugdata.target_milestone != version.number:
                validator.warn(
                    f"Version mismatch! target_milestone set to {bugdata.target_milestone} but hg says {version.number}"
                )

        else:
            validator.warn(
                f"Bug {patch.bug} is not for NSS ({bugdata.product}). Odd. Skipping."
            )
            continue

        if bugdata.status not in ["RESOLVED", "VERIFIED"]:
            validator.warn(
                f"Status is not resolved! bug set to {bugdata.status}. Skipping."
            )
            continue

        bugs[bugdata.id] = bugdata

    if not bugs:
        print("No patches found")
        return

    if options.html:
        with io.StringIO() as buf:
            print("<ul>", file=buf)
            for bugid, bugdata in bugs.items():
                sec = "🔐 " if bugdata.groups else ""
                print(
                    f'  <li><a href="{bugdata.weburl}">{sec}Bug {bugid}</a> - {bugdata.summary}</li>',
                    file=buf,
                )
            print("</ul>", file=buf)

            print("\n\n")
            print(buf.getvalue())

            pyperclip.copy(buf.getvalue())
            print("(Copied to clipboard)")

    # Derive the new contributors list
    contributorsRevRange = f"reverse(ancestors({contribListLastHash.decode('utf-8')}^))"
    print(f"Gathering new contributors list ({contributorsRevRange})...")
    for commit in hgclient.log(revrange=contributorsRevRange):
        patch = Patch(commit=commit, validator=NullValidator())
        contribList.observe(patch.author.decode("utf-8"), previousRelease=True)

    print("(Apparently) new contributors:")
    for author in sorted(contribList.list(limitToNewContributors=True)):
        print(f"{author}")


if __name__ == "__main__":
    main()
