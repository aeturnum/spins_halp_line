from quart import Response, Request
from typing import Optional

from spins_halp_line.player import Player
from spins_halp_line.util import PhoneNumber

#
# POST http://drex.space/tipline/start
# Headers:
#   Remote-Addr: 127.0.0.1
#   X-Real-Ip: 18.207.187.135
#   X-Forwarded-For: 18.207.187.135
#   Host: drex.space
#   Connection: upgrade
#   Content-Length: 490
#   Content-Type: application/x-www-form-urlencoded; charset=UTF-8
#   X-Twilio-Signature: zsdPQVb3M3K4acwcM57QEskr2Fs=
#   I-Twilio-Idempotency-Token: 4f2e8fd5-6bb0-4e8e-840e-0bc9d828a22e
#   User-Agent: TwilioProxy/1.1
# Form:
# 	AccountSid: AC0f154015eb5c3c108fb6d7c72bd238a9
# 	ApiVersion: 2010-04-01
# 	CallSid: CA02a16f4e87507937a4a60d2219a2c2bb
# 	CallStatus: ringing
# 	Called: +12513192351
# 	CalledCity:
# 	CalledCountry: US
# 	CalledState: AL
# 	CalledZip:
# 	Caller: +14156864014
# 	CallerCity: SAN RAFAEL
# 	CallerCountry: US
# 	CallerState: CA
# 	CallerZip: 94903
# 	Direction: inbound
# 	From: +14156864014
# 	FromCity: SAN RAFAEL
# 	FromCountry: US
# 	FromState: CA
# 	FromZip: 94903
# 	StirVerstat: TN-Validation-Passed-A
# 	To: +12513192351
# 	ToCity:
# 	ToCountry: US
# 	ToState: AL
# 	ToZip:


# todo: add _loaded guards that throw exceptions
class TwilRequest(object):

    def __init__(self, request: Request):
        self.req = request
        self._loaded = False
        self._data = {}
        self.player: Optional[Player] = None

    async def load(self):
        if not self._loaded:
            if self.content_type:
                if 'x-www-form-urlencoded' in self.content_type:
                    self._data = await self.req.form
                elif 'json' in self.content_type:
                    self._data = await self.req.form

            if self.caller:
                self.player = Player(self.caller)
                await self.player.load()

            self._loaded = True

        return self

    @property
    def data(self):
        return self._data

    @property
    def caller(self) -> Optional[PhoneNumber]:
        if "From" in self.data:
            return PhoneNumber(self.data.get("From"))
        return None

    @property
    def num_called(self) -> Optional[PhoneNumber]:
        if "Called" in self.data:
            return PhoneNumber(self.data.get("Called"))
        return None

    @property
    def digits(self):
        return self.data.get("Digits", None)

    @property
    def content_type(self):
        return self.headers.get('Content-Type', None)

    @property
    def method(self):
        return self.req.method

    @property
    def url(self):
        return self.req.url

    @property
    def headers(self):
        return self.req.headers

    @property
    def args(self):
        return self.req.args

    def str(self, label=""):
        s = []

        if label:
            s.append(f"{label}:")
        s.append(f"{self.method} {self.url}")
        s.append("Headers:")
        for header, value in self.headers.items():
            s.append(f'  {header}: {value}')

        if self.args:
            s.append("Args:")
            for arg, value in self.args.items():
                s.append(f'   {arg}: {value}')

        if self.data:
            s.append("Body:")
            for arg, value in self.data.items():
                s.append(f'  {arg}: {value}')

        return "\n".join(s)

    def __str__(self):
        sigil = "?"
        if self._loaded:
            sigil = "X"
            if self.caller:
                sigil = self.caller.friendly

        return f'TR[{sigil}]'


def t_resp(response):
    resp = Response(str(response))
    resp.headers['Content-Type'] = 'text/xml'
    return resp
