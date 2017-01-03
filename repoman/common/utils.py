#!/usr/bin/env python
import glob
import logging
import os
import pprint
import shutil
import string
import subprocess
import sys
from functools import partial

import requests
import gnupg


logger = logging.getLogger(__name__)


class NotSamePackage(Exception):
    """Thrown when trying to compare different packages"""
    pass


def get_gpg(homedir=os.path.expanduser('~/.gnupg'), use_agent=False):
    try:
        # older gnupg
        gpg = gnupg.GPG(gnupghome=homedir, use_agent=use_agent)
    except TypeError:
        gpg = gnupg.GPG(homedir=homedir, use_agent=use_agent)
    return gpg


def gpg_load_key(key_path, gpg=None):
    logger.debug('Loading key %s', key_path)
    gpg = gpg if gpg is not None else get_gpg()
    with open(key_path) as key_fd:
        skey = gpg.import_keys(key_fd.read())
        fprint = skey.results[0]['fingerprint']
    logger.debug('Loaded key %s with fingerprint %s', key_path, fprint)
    return fprint


def gpg_get_keyuid(key_path, gpg=None):
    logger.debug('Looking the uid for %s', key_path)
    gpg = gpg if gpg is not None else get_gpg()
    fprint = gpg_load_key(key_path=key_path, gpg=gpg)
    keyuid = None
    for key in gpg.list_keys(True):
        if key['fingerprint'] == fprint:
            keyuid = key['uids'][0]
    if not keyuid:
        for key in gpg.list_keys():
            if key['fingerprint'] == fprint:
                keyuid = key['uids'][0]
    if not keyuid:
        raise Exception('Failed to get uid for key %s' % key_path)
    logger.debug('Got uid %s for %s', keyuid, key_path)
    return keyuid


def gpg_unlock(key_path, use_agent=True, passphrase=None, gpg=None):
    logger.debug('Unlocking gpg key %s' % key_path)
    gpg = gpg if gpg is not None else get_gpg(
        homedir=None,
        use_agent=use_agent,
    )
    key_uid = gpg_get_keyuid(key_path=key_path, gpg=gpg)
    sign = partial(
        gpg.sign,
        message='Dummy_message',
        keyid=key_uid,
    )
    if passphrase:
        sign(passphrase=passphrase)
    else:
        sign()
    logger.debug('Unlocked gpg key %s' % key_path)
    return gpg


def response2str(response):
    return (
        'URL: {url}\n'
        'Status: {status_code}\n'
        'Reason: {reason}\n'
        'Headers: {headers}\n'
        'Body: {text}\n'
    ).format(
        url=response.url,
        status_code=response.status_code,
        reason=response.reason,
        headers=pprint.pformat(dict(response.headers)),
        text=response.text.encode('utf-8'),
    )


def get_plugins(plugin_dir=None):
    """
    Given a path, returns the importable files and directories in it
    """
    plugin_dir = plugin_dir or os.path.dirname(__file__)
    modules = []
    for module in glob.glob(plugin_dir + "/*"):
        if not module.endswith('.py') \
           and not os.path.isdir(module):
            continue
        if module.endswith('__init__.py'):
            continue
        if module.endswith('.py'):
            modules.append(os.path.basename(module)[:-3])
        elif (
            os.path.isdir(module) and
            os.path.isfile(module + '/__init__.py')
        ):
            modules.append(os.path.basename(module))
    return modules


def find_recursive(base_path, fmatch):
    """
    Walks a directory recursively and returns the list of files for which
    fmatch(filename) returns True
    """
    logger.debug('Recursively looking into %s', base_path)
    matched_files = []
    for root, _, files in os.walk(base_path):
        matched_files.extend([
            os.path.join(root, fname)
            for fname in files
            if fmatch(fname)
        ])
    logger.debug('Got matched artifacts: %s', matched_files)
    return matched_files


def tryint(mayint):
    """
    Tries to cast to int, and returns the same object if failed.
    """
    try:
        return int(mayint)
    except ValueError:
        return mayint


def cmpver(ver1, ver2):
    """
    Compares two version in a natural sort ordering fashion (what you usually
    expect when comparing versions yourself).
    Thought for version strings in the form:
       x.y.z

    The return value macthes cmp() function and is negative if ver1 < ver2,
    zero if ver1 == ver2 and strictly positive if ver1 > ver2.
    """
    ver1 = '.' in ver1 and ver1.split('.') or (ver1,)
    ver2 = '.' in ver2 and ver2.split('.') or (ver2,)
    ver1 = [tryint(i) for i in ver1]
    ver2 = [tryint(i) for i in ver2]
    if ver1 > ver2:
        return 1
    if ver1 == ver2:
        return 0
    else:
        return -1


def cmpfullver(fullver1, fullver2):
    """
    Compares version strings in the form:
       x.y.z-a.b.c
    """
    ver1, rel1 = split(fullver1, '-', 1)
    ver2, rel2 = split(fullver2, '-', 1)
    ver_res = cmpver(ver1, ver2)
    if ver_res != 0:
        return ver_res
    return cmpver(rel1, rel2)


def print_busy(prev_pos=0):
    """
    Shows a spinning bar when called like this:
    > i=0
    > while True:
    >    i = print_busy(i)
    """
    sys.stdout.write('\r')
    if prev_pos == 0:
        sys.stdout.write('-')
    elif prev_pos == 1:
        sys.stdout.write('/')
    elif prev_pos == 2:
        sys.stdout.write('|')
    else:
        sys.stdout.write('\\')
    sys.stdout.flush()
    return (prev_pos + 1) % 4


def to_human_size(fsize):
    """
    Pass a number from bytes, to human readable form, using 1024 multiples.
    """
    mb = fsize / (1024 * 1024)
    if mb >= 1:
        return '%dM' % mb
    kb = fsize / 1024
    if kb >= 1:
        return '%dK' % kb
    return '%dB' % fsize


def download(path, dest_path, tries=3, verify=True):
    """
    Download a package from a url.
    """
    headers = requests.head(path, verify=verify)
    chunk_size = 4096
    # length == 0 means that we don't know the size
    length = int(headers.headers.get('content-length', 0)) or 0
    logging.info('Downloading %s, length %s ...',
                 path,
                 length and to_human_size(length) or 'unknown')
    num_dots = 100
    dot_frec = (length / num_dots) or 1
    stream = requests.get(path, stream=True, verify=verify)
    while not stream and tries:
        stream = requests.get(path, stream=True, verify=verify)
        tries -= 1
    if not tries:
        raise Exception(
            'Failed to download %s\n\tcode: %d\n\treason: %s' %
            (stream.url, stream.status_code, stream.reason)
        )
    prev_percent = 0
    progress = 0
    if length:
        cur_percent = 0
        sys.stdout.write(
            '    %[' +
            '-' * 23 + '25' + '-' * 24 +
            '50' +
            '-' * 23 + '75' + '-' * 24 +
            ']\r' + '    %['
        )
    sys.stdout.flush()
    with open(dest_path, 'w') as rpm_fd:
        for chunk in stream.iter_content(chunk_size=chunk_size):
            if chunk:
                rpm_fd.write(chunk)
                progress += len(chunk)
                cur_percent = int(progress / dot_frec)
                if length and cur_percent > prev_percent:
                    for _ in xrange(cur_percent - prev_percent):
                        sys.stdout.write('=')
                    sys.stdout.flush()
                    prev_percent = cur_percent
                elif not length:
                    prev_percent = print_busy(prev_percent)
    if length:
        if cur_percent < num_dots:
            sys.stdout.write('=')
        sys.stdout.write(']\n')
        sys.stdout.flush()
    else:
        sys.stdout.flush()
        logging.info('    Done')


def copy(what, where):
    """Try to link, try to copy if cross-device"""
    try:
        os.link(what, where)
    except OSError as oerror:
        if oerror.errno == 18:
            shutil.copy2(what, where)
        else:
            logging.error('cannot copy %s on %s' % (what, where))
            raise


def extract_sources(rpm_path, dst_dir, with_patches=False):
    """
    Extract the source files fro  a srcrpm, uses rpm2cpio

    :param rpm_path: Path to the srcrpm
    :param dst_dir: Destination directory to hold the sources, will create it
        if it does not exist
    :param with_patches: if set to True, extract also the .patch files if any
    """
    if not os.path.isdir(dst_dir):
        os.makedirs(dst_dir)
    oldpath = os.getcwd()
    if not dst_dir.startswith('/'):
        dst_dir = oldpath + '/' + dst_dir
    if not rpm_path.startswith('/'):
        rpm_path = oldpath + '/' + rpm_path
    dst_path = dst_dir + '/' + rpm_path.rsplit('/', 1)[-1]
    copy(rpm_path, dst_path)
    os.chdir(dst_dir)
    try:
        rpm2cpio = subprocess.Popen(['rpm2cpio', dst_path],
                                    stdout=subprocess.PIPE)
        cpio_cmd = ['cpio', '-iv', '*gz', '*.zip', '*.7z', '*.xz']
        if with_patches:
            cpio_cmd.append('*.patch')
        with open(os.devnull, 'w') as devnull:
            cpio = subprocess.Popen(
                cpio_cmd,
                stdin=rpm2cpio.stdout,
                stdout=devnull,
                stderr=devnull,
            )
        rpm2cpio.stdout.close()
        (stdout, stderr) = cpio.communicate()
        if cpio.returncode != 0:
            raise Exception(
                "Failed to extract sources:\n== STDOUT:\n%s\n== STDERR:\n%s",
                stdout,
                stderr,
            )
    finally:
        os.chdir(oldpath)
        os.remove(dst_path)


def sign_file(gpg, fname, keyid, passphrase, detach=True):
    with open(fname) as f_desc:
        try:
            # old gnupg
            signature = gpg.sign_func(
                f_desc,
                keyid=keyid,
                passphrase=passphrase,
                detach=True,
                binary=False,
            )
        except AttributeError:
            signature = gpg.sign_file(
                f_desc,
                keyid=keyid,
                passphrase=passphrase,
                detach=True,
                clearsign=False,
                binary=False,
            )
    if not signature.data:
        raise Exception(
            "Failed to sign file %s: \n%s",
            file,
            signature.stderr
        )
    with open(fname + '.sig', 'w') as sfd:
        sfd.write(signature.data)


def sign_detached(src_dir, key, passphrase=None):
    """
    Create the detached signatures for the files in the specified dir.

    :param src_dir: File to sign or directory with files to sign (recursively)
    :param key: Key to sign the sources with
    :param passphrase: Passphrase for the given key
    """
    oldpath = os.getcwd()
    if not src_dir.startswith('/'):
        src_dir = oldpath + '/' + src_dir
    try:
        # older gnupg
        gpg = gnupg.GPG(gnupghome=os.path.expanduser('~/.gnupg'))
    except TypeError:
        gpg = gnupg.GPG(homedir=os.path.expanduser('~/.gnupg'))
    with open(key) as key_fd:
        skey = gpg.import_keys(key_fd.read())
    fprint = skey.results[0]['fingerprint']
    keyid = None
    for user_key in gpg.list_keys(True):
        if user_key['fingerprint'] == fprint:
            keyid = user_key['keyid']
    if os.path.isdir(src_dir):
        for dname, _, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith('.sig'):
                    continue
                sign_file(
                    gpg=gpg,
                    fname=os.path.join(dname, fname),
                    keyid=keyid,
                    passphrase=passphrase,
                )
    else:
        fname = src_dir
        sign_file(
            gpg=gpg,
            fname=fname,
            keyid=keyid,
            passphrase=passphrase,
        )


def save_file(src_path, dst_path):
    """
    Save a file to a specific new path if not there already. Will create the
    path tree if it does not exist already.

    :param src_path: Source path for the package
    :param dst_path: New path to save the package to
    """
    if os.path.exists(dst_path):
        logging.debug('Not saving %s, already exists', dst_path)
        return
    logging.info('Saving %s', dst_path)
    if not os.path.exists(dst_path.rsplit('/', 1)[0]):
        os.makedirs(dst_path.rsplit('/', 1)[0])
    copy(src_path, dst_path)


def list_files(path, extension):
    '''Find all the files with the given extension under the given dir'''
    files_found = []
    for root, _, files in os.walk(path):
        for fname in files:
            if fname.endswith(extension):
                files_found.append(root + '/' + fname)
    return files_found


def split(what, separator, num_results=None):
    if num_results is None:
        return what.split(separator)
    res = what.split(separator, num_results)
    res.extend([''] * (num_results - len(res) + 1))
    return res


def rsplit(what, separator, num_results=None):
    if num_results is None:
        return what.rsplit(separator)
    res = what.rsplit(separator, num_results)
    res.extend([''] * (num_results - len(res) + 1))
    return res


def get_last(what, num):
    if len(what) >= num:
        return what[:num]
    else:
        what = what[:]
        what.extend([None] * (num - len(what)))
        return what


def sanitize_file_name(file_name, replacement='_'):
    """
    Replaces any unwanted characters from the given file or dir name with the
    given replacement string

    Args:
        file_name (str): file or directory name to sanitize
        replacement (str): what to put in place of the bad chars

    Returns:
        str: sanitized name with all the bad chars replaced

    Example:
        >>> sanitize_file_name("I'm an /ugly%#@!")
        'I_m an _ugly____'
        >>> sanitize_file_name("I'm an /ugly%#@!", replacement='-')
        'I-m an -ugly----'
    """
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    return ''.join(
        c if c in valid_chars else replacement
        for c in file_name
    )


def create_symlink(basepath, dest, link):
    """
    Creates a symlink

    Args:
        basepath(str): Path to creat the simlink on
        dest(str): Path not relative to basepath of the destination for the
            link
        link(str): Path relative to basepath of the link itself

    Returns:
        None
    """
    full_link = os.path.join(basepath, link)
    logger.info('  %s -> %s', full_link, dest)
    if os.path.lexists(full_link):
        logger.warn('    Path for the link already exists')
        return

    if not os.path.exists(dest):
        logger.warn('   The link points to non-existing path')
    try:
        os.symlink(dest, full_link)
    except Exception as exc:
        logger.error(
            '    Failed to create link %s -> %s',
            full_link,
            dest,
        )
        raise exc
