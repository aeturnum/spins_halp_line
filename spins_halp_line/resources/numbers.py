import json
import random
from typing import Union, List, Dict, Optional

import trio
import phonenumbers

# Helper class to normalize number formats
class PhoneNumber:

    def __init__(self, number: Union[str, int, 'PhoneNumber']):
        if isinstance(number, PhoneNumber):
            # This is to allow us to construct PhoneNumbers everywhere and not worry about nesting
            self._e164 = number._e164
        else:
            self._e164 = self._parse(number)

    # This is a rough, hand-rolled method for dealing with numbers
    def _parse(self, number) -> phonenumbers.PhoneNumber:
        if isinstance(number, int):
            number = str(number)

        try:
            # check for a clean e164
            number = phonenumbers.parse(number)
        except phonenumbers.phonenumberutil.NumberParseException:
            # if this throws just let it fly
            number = phonenumbers.parse("+1" + number)

        return number

    def __eq__(self, other):
        if isinstance(other, PhoneNumber):
            return self.e164 == other.e164
        elif isinstance(other, str):
            if other == '*':
                return True # We are always equal to '*'
            return self == PhoneNumber(other)

        return False

    # todo: I keep fucking up and putting PhoneNumbers directly into dictionaries that will get serialized to JSON. Now, this should be an easy thing to handle - a PhoneNumber has a simple way to be serialized (.e164), but it doesn't seem like the standard `json` library has an interface on objects that it'll use to serialize non-standard things.# todo:

    # todo: So, we have three options:
    # todo: - add a central json helper file which we route all json encode / decode calls through, and which has a subclass of JsonEncoder that will handle phone numbers properly
    # todo: - find another JSON library that *does* have a standardized serialize call that it'll call on objects it doesn't know how to seralize
    # todo: - add code that checks to make sure we aren't adding non-basic objects to states (probably the hardest solution)

    def __hash__(self):
        return hash(self.e164)

    def toJson(self):
        return self.e164

    # Used for twilio purposes
    @property
    def e164(self):
        return phonenumbers.format_number(self._e164, phonenumbers.PhoneNumberFormat.E164)

    @property
    def friendly(self):
        if self._e164.country_code == 1:
            # If in the US or Canada, just do national
            return phonenumbers.format_number(self._e164, phonenumbers.PhoneNumberFormat.NATIONAL)
        else:
            # Otherwise international
            return phonenumbers.format_number(self._e164, phonenumbers.PhoneNumberFormat.INTERNATIONAL)

    def __repr__(self):
        return self.e164

    def __str__(self):
        return self.friendly

# Singleton for loading and dispensing numbers and organizing capabilities
class NumberLibrary:

    _Capabilities = {
        "voice",
        "sms",
        "mms"
    }

    def __init__(self, number_file="./numbers.json"):
        self._file_path = number_file
        self.master_index: List[str] = [] # raw list of phone numbers
        self.capabilities: Dict[str, set] = {} # capabilities index
        self.labels: Dict[str, str] = {}

    async def load(self):
        # json format
        # number is e164 format!
        # number and capabilities are required or we will crash in protest
        # [
        #   {
        #       "number": "+15102567675",
        #       "labels": ["Clave1"]
        #       "capabilities": ["voice", "sms", "mms"]
        #   }
        # ]

        # If any of this throws an exception we just wanna unroll the server
        async with await trio.open_file(self._file_path) as f:
            dict_array = json.loads(await f.read())
            for num_info in dict_array:
                self.master_index.append(num_info['number'])
                capability_list = num_info['capabilities']
                labels = num_info.get('labels', [])
                # get the number we just inserted to keep our references straight
                number = self.master_index[-1]

                for label in labels:
                    self.labels[label] = number

                for cap in capability_list:
                    if cap not in self.capabilities:
                        self.capabilities[cap] = set()

                    self.capabilities[cap].add(number)

    @property
    def voice(self):
        return {"voice"}

    @property
    def sms(self):
        return {"sms"}

    @property
    def mms(self):
        return {"mms"}

    @property
    def voice_and_sms(self):
        return self.voice.union(self.sms)

    @property
    def all_capabilities(self):
        return self.voice.union(self.sms).union(self.mms)

    def random(self, capabilities:Optional[set]=None) -> PhoneNumber:
        if not capabilities:
            capabilities = self.voice

        candidates = self.master_index
        for cap in capabilities:
            candidates = [c for c in candidates if c in self.capabilities[cap]]

        return PhoneNumber(random.choice(candidates))

    def from_label(self, label: str) -> PhoneNumber:
        if label in self.labels:
            return PhoneNumber(self.labels[label])


Global_Number_Library = NumberLibrary()
