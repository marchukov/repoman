#!/usr/bin/env python
import logging

import requests
import requests.packages.urllib3 as urllib3


RETRY_PROTOCOL_PREFIXES = ('http://', 'https://')
CHUNK_SIZE = 4096


logger = logging.getLogger(__name__)


def to_file(url, dest_file):
    """
    Download content from a url to a local file.
    """

    with open(dest_file, 'w') as target:
        to_fd(url, target)


def to_fd(url, fd):
    """
    Download content from a url to a file descriptor.
    """

    with make_session_object() as session:
        stream = session.get(url, stream=True, verify=True)
        for chunk in stream.iter_content(chunk_size=CHUNK_SIZE):
            fd.write(chunk)


def make_retry_object():
    """
    Return configured urllib3.util.Retry object
    """

    return urllib3.util.retry.Retry(total=5, backoff_factor=1)


def make_adapter_object():
    """
    Return configured connection adapter.
    """

    retry = make_retry_object()
    return requests.adapters.HTTPAdapter(max_retries=retry)


def make_session_object():
    """
    Return configured requests session object.
    """

    session = requests.Session()
    for prefix in RETRY_PROTOCOL_PREFIXES:
        session.mount(prefix, make_adapter_object())
    return session
