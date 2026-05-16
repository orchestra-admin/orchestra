# Re-export from core.secrets for backward compatibility.
# New code should import directly from core.secrets.
from orchestra_core.secrets import (  # noqa: F401
    get_secret,
    set_secret,
)