#!/usr/bin/env python
import logging

import requests


logger = logging.getLogger(__name__)


def to_file(url, dest_file):
    """
    Download content from a url to a local file.
    """

    with open(dest_file, 'w') as target:
        download_to_fd(url, target, verify)


def to_fd(url, fd):
    """
    Download content from a url to a file descriptor.
    """

    with requests.Session() as session:
        stream = session.get(url, stream=True, verify=True)
        for chunk in stream.iter_content():
            fd.write(chunk)
