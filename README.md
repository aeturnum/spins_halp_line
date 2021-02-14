# Experimental Async Storytelling Server

This server was built to deliver an immersive experience art project where players believe they are calling one number, 
but get pulled into unexpected adventures along the way. This is done using phone calls, texts and puzzles.

## Library Choices

In the spirit of building an experimental platform, this server is built entirely on the Trio async library and 
its associated libraries. That's why, for instance, the 'database' is `redis` (lol). Of course, this generated a lot of
headaches for practically getting things done, but that's part of learning!

That's all to say: no library was selected out of the impression that it's the best for the job. Don't look to this 
project's `pyproject.toml` for good taste. Libraries were selected expiermentally and, when possible, the source
contains notes about how that came out.

## Installing

The one recommendation I do make is [poetry](https://python-poetry.org/) for Python library management! It's great!

The [poetry docs](https://python-poetry.org/docs/) have installation instructions.

```
git clone https://github.com/aeturnum/spins_halp_line
cd spins_halp_line
poetry install 
poetry run spins_halp_line/server.py
```