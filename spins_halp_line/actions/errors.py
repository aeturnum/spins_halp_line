from twilio import rest

from spins_halp_line.util import Logger
from spins_halp_line.constants import Credentials
from spins_halp_line.resources.numbers import PhoneNumber, Global_Number_Library
from .twilio import send_sms


# This is a file for handling errors and may be imported from nearly anywhere.

async def error_sms(message_text, logger: Logger = None):
    # generally we try to synchronize use of this but we need it now
    client = rest.Client(Credentials["twilio"]["sid"], Credentials["twilio"]["token"])
    from_num = Global_Number_Library.random({"sms"})  # any number that can text

    # todo: maybe add another untracked file for this? It's not exactly a credential?
    for number in Credentials.get('error_reports', {}).get('numbers_to_text', []):
        try:
            number = PhoneNumber(number)
            await send_sms(from_num, number, message_text, client=client)
        except Exception as e:
            s = f'Entry {number} in Credentials["error_reports"]({Credentials.get("error_reports")}) - had an error: {e}'
            if logger:
                logger.e(s)
            else:
                print(s)
