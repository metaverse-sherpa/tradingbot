def fetch_crypto_balance():
    return 10.0, True

import sys
sys.path.append('.')
from utils import run_with_timeout
res = run_with_timeout(fetch_crypto_balance, 6.0, (0.0, False))
print(res)
