"""Keep the normal test suite independent from a beta-mode shell environment."""
import os

os.environ["ALIGN_BETA_MODE"] = "0"
os.environ["ALIGN_BREACH_CHECK"] = "0"
os.environ["ALIGN_OWNER_TOTP"] = "optional"
