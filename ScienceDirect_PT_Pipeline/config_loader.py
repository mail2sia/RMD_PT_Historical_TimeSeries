import json
import random
import itertools
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

def load_config():
    with open(_CONFIG_PATH, encoding="utf-8") as config_file:
        config = json.load(config_file)
    return config["apikeys"]["elsevier"]

SCOPUS_API_KEYS = load_config()
random.shuffle(SCOPUS_API_KEYS)
API_KEYS_CYCLE = itertools.cycle(SCOPUS_API_KEYS)

def get_next_api_key():
    return next(API_KEYS_CYCLE)
