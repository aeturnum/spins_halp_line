import logging
from typing import Union, Optional, IO

import hypercorn.logging as hyplog


# modified version of create logger
def our_create_logger(
    name: str,
    target: Union[logging.Logger, str, None],
    level: Optional[str],
    sys_default: IO,
    *,
    propagate: bool = True,
) -> Optional[logging.Logger]:
    if isinstance(target, logging.Logger):
        return target

    if target:
        logger = logging.getLogger(name)
        logger.handlers = [
            logging.StreamHandler(sys_default) if target == "-" else logging.FileHandler(target)
        ]
        logger.propagate = propagate
        formatter = logging.Formatter(
            "[%(levelname)s] %(message)s",
            "",
        )
        logger.handlers[0].setFormatter(formatter)
        if level is not None:
            logger.setLevel(logging.getLevelName(level.upper()))
        return logger
    else:
        return None

def do_monkey_patches():
    # who needs config options with python
    hyplog._create_logger = our_create_logger

async def pretty_print_request(r, label = ""):
    s = []
    content_type = r.headers.get("Content-Type", None)

    if label:
        s.append(f"{label}:")
    s.append(f"{r.method} {r.url}")
    s.append("Headers:")
    for header, value in r.headers.items():
        s.append(f'  {header}: {value}')

    if r.args:
        s.append("Args:")
        for arg, value in r.args.items():
            s.append(f'{arg}: {value}')

    if content_type:
        if 'x-www-form-urlencoded' in content_type:
            form = await r.form
            s.append("Form:")
            for arg, value in form.items():
                s.append(f'{arg}: {value}')
        if 'json' in content_type:
            json = await r.get_json()
            s.append("JSON:")
            for arg, value in json.items():
                s.append(f'{arg}: {value}')

    print("\n".join(s))