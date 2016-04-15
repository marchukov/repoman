#!/usr/bin/env python
"""
This program is a helper to repo management

Started as specific for rpm files, but was modified to be able to support
different types of artifacts
"""
import argparse
import logging
import sys
from getpass import getpass


from .common.config import Config
from .common.repo import Repo
from .common.stores import STORES
from .common.sources import SOURCES


LOGGER = logging.getLogger(__name__)


def add_generate_src_parser(parent_parser):
    generate_src = parent_parser.add_parser(
        'generate-src',
        help='Populate the src dir with the tarballs from the src.rpm '
        'files in the repo'
    )
    generate_src.add_argument(
        '-p', '--with-patches', action='store_true',
        help='Include the patch files'
    )
    return parent_parser


def add_createrepo_parser(parent_parser):
    parent_parser.add_parser(
        'createrepo',
        help='Run createrepo on each distro repository.'
    )
    return parent_parser


def add_remove_old_parser(parent_parser):
    remove_old = parent_parser.add_parser(
        'remove-old',
        help='Remove old versions of packages.'
    )
    remove_old.add_argument(
        '-k', '--keep', type=int, default=1,
        help='Number of versions to keep'
    )

    return parent_parser


def add_sign_rpms_parser(parent_parser):
    parent_parser.add_parser(
        'sign-rpms',
        help='Sign all the packages.'
    )

    return parent_parser


def add_add_artifact_parser(parent_parser):
    add_artifact = parent_parser.add_parser('add', help='Add an artifact')
    add_artifact.add_argument(
        '-t', '--temp-dir', action='store', default=None,
        help='Temporary dir to use when downloading artifacts'
    )
    add_artifact.add_argument(
        'artifact_source', nargs='*',
        help=(
            'An artifact source to add, it can be one of: '
            'conf:path_to_file will load all the sources from that file, '
            'conf:stdin wil read the sources from stdin'
            + ', '.join(
                ', '.join(source.formats_list())
                for source in SOURCES.itervalues()
            )
        )
    )
    add_artifact.add_argument(
        '--keep-latest', required=False, type=int, metavar='NUM',
        default=0, help=(
            'If passed, will remove all the artifact versions but the latest '
            'NUM'
        )
    )

    return parent_parser


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-n', '--noop', action='store_true')
    parser.add_argument(
        '-c', '--config', action='store', default=None,
        help='Configuration file to use',
    )
    parser.add_argument(
        '-o', '--option', action='append', default=[],
        help='Extra config option as in the config file, in the form '
        'section.name=value',
    )
    parser.add_argument(
        '-t', '--temp-dir', action='store', default=None,
        help='Temporary directory to use, will generate it if not passed',
    )
    parser.add_argument(
        '-s', '--stores', required=False, default=','.join(STORES.keys()),
        help='Store classes to take into account when loading the '
        'repo. Available ones are %s' % ', '.join(STORES.keys()))
    parser.add_argument(
        'dir',
        help=(
            "Directory of the repo. If there's a source entry in the form "
            "repo-suffix:some_string, then that 'some_string' will be "
            "postpended to the repo name"
        )
    )
    parser.add_argument(
        '-k', '--key', required=False,
        help='Path to the key to use when signing, will not sign any '
        'artifacts if not passed.'
    )
    parser.add_argument(
        '--passphrase', required=False, default='ask',
        help='Passphrase to unlock the singing key'
    )
    parser.add_argument(
        '--with-sources', required=False, action='store_true',
        help='Generate the sources tree.'
    )
    repo_subparser = parser.add_subparsers(dest='repoaction')
    repo_subparser = add_add_artifact_parser(repo_subparser)
    repo_subparser = add_generate_src_parser(repo_subparser)
    repo_subparser = add_createrepo_parser(repo_subparser)
    repo_subparser = add_remove_old_parser(repo_subparser)
    repo_subparser = add_sign_rpms_parser(repo_subparser)

    return parser.parse_args()


def setup_verbose_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format=(
            '%(asctime)s::%(levelname)s::'
            '%(name)s.%(funcName)s:%(lineno)d::'
            '%(message)s'
        ),
    )
    logging.root.level = logging.DEBUG
    #  we want connectionpool debug logs
    logging.getLogger('requests').setLevel(logging.DEBUG)
    logging.debug('Enabled verbose mode')


def setup_regular_logging():
    logging.basicConfig(
        level=logging.INFO,
        format=(
            '%(asctime)s::%(levelname)s::'
            '%(name)s::'
            '%(message)s'
        ),
    )
    LOGGER.root.level = logging.INFO
    #  we don't want connectionpool info logs
    logging.getLogger('requests').setLevel(logging.ERROR)


def handle_custom_options(args, config):
    for opt_val in args.option:
        if '=' not in opt_val:
            raise Exception('Invalid option passed %s' % opt_val)
        opt, val = opt_val.split('=')
        if '.' not in opt:
            raise Exception('Invalid option passed %s' % opt_val)
        sect, opt = opt.rsplit('.', 1)
        config.add_to_section(sect, opt, val)

    return config


def set_signing_key(config):
    if not config.get('signing_key', ''):
        config.set(
            'signing_key',
            raw_input('Path to the signing key: '),
        )

    if (
        config.get('signing_key', '')
        and not config.get('signing_passphrase')
        or config.get('signing_passphrase') == 'ask'
    ):
        passphrase = getpass('Enter key passphrase: ')
        config.set('signing_passphrase', passphrase)

    return config


def has_to_handle_signing_key(args, config):
    return (
        config.get('signing_key', '')
        and config.get('signing_passphrase') == 'ask'
        or
        args.repoaction == 'sign-rpms'
    )


def setup_logging(verbose=False):
    if verbose:
        setup_verbose_logging()
    else:
        setup_regular_logging()


def get_config(args):
    if args.config:
        config = Config(path=args.config)
    else:
        config = Config()

    config = handle_custom_options(args, config)

    if args.temp_dir:
        config.set('temp_dir', args.temp_dir)

    if args.stores:
        config.set('stores', args.stores)

    if args.with_sources:
        config.set('with_sources', 'true')

    if args.key:
        config.set('signing_key', args.key)
        config.set('signing_passphrase', args.passphrase)

    if has_to_handle_signing_key(args, config):
        config = set_signing_key(config)

    return config


def get_repo(args, config):
    if args.dir.endswith('/'):
        path = args.dir[:-1]
    else:
        path = args.dir

    repo = Repo(path=path, config=config)
    return repo


def do_add(args, config, repo):
    if args.keep_latest < 0:
        LOGGER.error('keep-latest must be >0')
        return 1

    LOGGER.info('Adding artifacts to the repo %s', repo.path)
    for art_src in args.artifact_source:
        repo.add_source(art_src.strip())

    if args.keep_latest > 0:
        header_msg = 'Removed'
        if args.noop:
            header_msg = 'Would have removed'
        # save beforehand to make sure that the rpm's inodes point to the new
        # repo before removing them
        repo.save()
        for artifact in repo.delete_old(
            num_to_keep=args.keep_latest,
            noop=args.noop
        ):
            LOGGER.info('%s %s', header_msg, artifact.path)
    else:
        LOGGER.info('')

    repo.save()
    return 0


def do_remove_old(args, config, repo):
    if args.keep <= 0:
        LOGGER.error('keep must be >0')
        return 1

    header_msg = 'Removed'
    if args.noop:
        header_msg = 'Would have removed'
    for artifact in repo.delete_old(
        num_to_keep=args.keep,
        noop=args.noop
    ):
        logging.info('%s %s', header_msg, artifact)

    repo.save()


def do_generate_src(config, repo):
    config.set('with_sources', 'true')
    repo.save()
    return 0


def main():
    args = parse_args()

    setup_logging(args.verbose)

    config = get_config(args)
    repo = get_repo(args, config)

    LOGGER.info('')
    exit_code = 0
    if args.repoaction == 'add':
        exit_code = do_add(args, config, repo)
    elif args.repoaction == 'generate-src':
        exit_code = do_generate_src(config, repo)
    elif args.repoaction == 'remove-old':
        exit_code = do_remove_old(args, config, repo)

    sys.exit(exit_code)
