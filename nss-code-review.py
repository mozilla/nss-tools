#!/usr/local/bin/python3

from whaaaaat import prompt
import yaml
import pyperclip
import io, os

__location__ = os.path.realpath(
  os.path.join(os.getcwd(), os.path.dirname(__file__)))

resultData = {}
checklistData = {}
with open(os.path.join(
            __location__, "nss-code-review-checklist.yaml"), "r") as inFile:
  checklistData = yaml.load(inFile, Loader=yaml.BaseLoader)

for segment in checklistData:
  for heading in segment:
    print(heading)

    resultData[heading] = {}

    for rule in segment[heading]:
      answers = prompt([
        {'type': 'confirm', 'name': 'checklist_item', 'message': rule},
      ])
      resultData[heading][rule] = answers['checklist_item']

with io.StringIO() as buf:

  for heading in resultData:
    print("**"+heading+"**", file=buf)
    for rule in resultData[heading]:
      if resultData[heading][rule]:
        print("✅ " + rule, file=buf)
      else:
        print("❌ " + rule, file=buf)
    print("", file=buf)

  print("", file=buf)
  print("[[ https://github.com/mozilla/nss-tools | nss-code-review.py ]]", file=buf)

  print("\n\n")
  print(buf.getvalue())

  pyperclip.copy(buf.getvalue())
  print("(Copied to clipboard)")