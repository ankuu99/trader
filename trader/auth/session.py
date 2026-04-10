from kiteconnect import KiteConnect

from trader.core.config import config
from trader.core.logger import get_logger

logger = get_logger(__name__)


def create_kite() -> KiteConnect:
    """
    Return an authenticated KiteConnect instance.

    Raises RuntimeError if no access token is available — caller should
    direct the user to run scripts/login.py to refresh it.
    """
    kite = KiteConnect(api_key=config.kite_api_key)

    token = config.kite_access_token
    if not token:
        raise RuntimeError(
            "No access token found. Run `python scripts/login.py` to authenticate."
        )

    kite.set_access_token(token)

    # Validate the token with a lightweight API call
    try:
        profile = kite.profile()
        logger.info("Authenticated as: %s (%s)", profile["user_name"], profile["user_id"])
    except Exception as e:
        raise RuntimeError(
            f"Access token is invalid or expired. "
            f"Run `python scripts/login.py` to re-authenticate. ({e})"
        )

    return kite
