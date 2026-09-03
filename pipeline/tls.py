"""TLS trust configuration.

On machines where antivirus (Avast, Kaspersky, ...) or a corporate proxy
performs HTTPS inspection, the interception root certificate is installed in
the OS trust store but *not* in certifi's bundle. ``requests`` (and ClearML,
which uses requests) then fail with::

    SSLError: certificate verify failed: unable to get local issuer certificate

Call :func:`configure_tls` once, before any network I/O, to resolve this.
"""

from __future__ import annotations

import os

from .logging_config import get_logger

logger = get_logger(__name__)


def configure_tls() -> str:
    """Point Python's TLS verification at a trust store that actually works.

    Resolution order:

    1. ``PIPELINE_CA_BUNDLE`` / ``REQUESTS_CA_BUNDLE`` env var -> use that PEM.
    2. The ``truststore`` package -> verify against the OS trust store
       (which contains the AV/proxy interception root).
    3. Fall back to certifi defaults and log a warning.

    Returns a short token describing what was applied (handy for logs/tests).
    """
    bundle = os.environ.get("PIPELINE_CA_BUNDLE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if bundle and os.path.isfile(bundle):
        os.environ["REQUESTS_CA_BUNDLE"] = bundle
        os.environ["SSL_CERT_FILE"] = bundle
        logger.info("TLS: using CA bundle %s", bundle)
        return f"ca-bundle:{bundle}"

    try:
        import truststore

        truststore.inject_into_ssl()
        logger.info("TLS: verifying against the OS trust store (truststore)")
        return "truststore"
    except ModuleNotFoundError:
        logger.warning(
            "TLS: truststore not installed and no CA bundle set; HTTPS may fail "
            "behind AV/proxy interception. Fix: `pip install truststore` or set "
            "PIPELINE_CA_BUNDLE=/path/to/corp-root-ca.pem"
        )
        return "certifi-default"
