"""Importing this module checks the whole environment and stops with every problem at once.

`production.py` imports it before `base`, because `base` itself stops at the first variable it
cannot read (the secret key, the database address). Running the full check first means a deploy
reports everything that is missing in one message instead of one variable per failed start.
"""

from config.env_check import enforce

enforce()
