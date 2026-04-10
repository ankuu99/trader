"""
Convenience wrapper — equivalent to:
    python main.py --config config/config_interday.yaml
"""
import os
os.environ["TRADER_CONFIG"] = "config/config_interday.yaml"

from main import main  # noqa: E402

if __name__ == "__main__":
    main()
