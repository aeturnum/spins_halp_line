from quart import Response, Request


class TwilRequest(object):

    def __init__(self, request: Request):
        self.req = request
        self._loaded = False
        self._data = {}

    async def _load(self):
        if self.content_type:
            if 'x-www-form-urlencoded' in self.content_type:
                self._data = await self.req.form
            elif 'json' in self.content_type:
                self._data = await self.req.form
    @property
    async def data(self):
        await self._load()
        return self._data

    @property
    async def number(self):
        return (await self.data).get("From", None)

    @property
    async def digits(self):
        return (await self.data).get("Digits", None)

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

    async def str(self, label=""):
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

        if await self.data:
            s.append("Body:")
            for arg, value in (await self.data).items():
                s.append(f'  {arg}: {value}')

        return "\n".join(s)




def t_resp(response):
    resp = Response(str(response))
    resp.headers['Content-Type'] = 'text/xml'
    return resp