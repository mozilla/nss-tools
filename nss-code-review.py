#!/usr/local/bin/python3

from whaaaaat import prompt
import yaml

resultData = {}
checklistData = {}
with open("nss-code-review-checklist.yaml", "r") as inFile:
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

print()
print()

for heading in resultData:
  print("**"+heading+"**")
  for rule in resultData[heading]:
    if resultData[heading][rule]:
      print("✅ " + rule)
    else:
      print("❌ " + rule)
  print()

print()
print("[[ https://github.com/mozilla/nss-tools | nss-code-review.py ]]")