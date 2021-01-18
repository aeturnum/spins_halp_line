import json

Script_New_State = "State_New"
Script_Any_Number = "*"
Script_Ignore_Change = 'State_Do_Not_Change'
Script_End_State = "State_End"

Root_Url = "https://drex.space"

Credentials = {}

try:
    with open("./creds.json", "r") as f:
        Credentials = json.loads(f.read())
except FileNotFoundError:
    pass