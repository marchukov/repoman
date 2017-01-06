#!/usr/bin/env python%
# encoding: utf-8
"""
This module holds the helper classes to represent an artifact list::

    Base_dir
    └── $name
        └── $version
            ├── $name-$version.$extension
            └── $name-$version.$extension.sig

This module has the classess that manage a set of artifacts, in a hierarchical
fashion, in the order::

    name 1-* version 1-* inode 1-* artifact-instance

So that translated to classes, with the first being the placeholder for the
whole data structure, is::

    ArtifactList 1-* ArtifactName 1-* ArtifactVersion \\
    1-* ArtifactInode 1-* Artifact

All except the Artifact class are implemented as subclasses of the python dict,
so as key-value stores.

For clarification, here's a dictionary like diagram::

    ArtifactList{
        name1: ArtifactName{
            version1: ArtifactVersion{
                inode1: ArtifactInode[Artifact, Artifact, ...]
                inode2: ArtifactInode[...]
            },
            version2: ArtifactVersion{...}
        },
        name2: ArtifactName{...}
    }

**NOTE**:You have to implement at least the Artifact class
"""
import os
import hashlib
import logging
from abc import (
    ABCMeta,
    abstractproperty,
)

from .utils import (
    download,
    cmpfullver,
    sign_detached,
)


logger = logging.getLogger(__name__)


class Artifact(object):
    __metaclass__ = ABCMeta

    def __init__(self, path, temp_dir='/tmp', verify_ssl=True):
        """
        :param path: Path or url to the artifact
        :param temp_dir: If url specified, will use that temporary dir to store
            it, the caller should take care of creating and deleting that
            temporary dir if needed
        """
        if path.startswith('http:') or path.startswith('https:'):
            name = path.rsplit('/', 1)[-1]
            if not name:
                raise Exception('Passed trailing slash in path %s, '
                                'unable to guess package name'
                                % path)
            fpath = temp_dir + '/' + name
            download(path, fpath, verify=verify_ssl)
            path = fpath
        self.path = path
        # will be calculated if needed
        self._md5 = None
        # this property should uniquely identify an artifact entity, in the
        # sense that if you have two rpms with the same full_name they must
        # package the same content or one of them is wrongly generated (the
        # version was not bumped or something)
        self.full_name = '%s(%s %s)' % (
            self.type, self.name, self.version,
        )

    @abstractproperty
    def version(self):
        pass

    @abstractproperty
    def extension(self):
        pass

    @abstractproperty
    def name(self):
        pass

    @abstractproperty
    def type(self):
        return 'artifact'

    @property
    def md5(self):
        """
        Lazy md5 calculation.
        """
        if self._md5 is None:
            with open(self.path) as fdno:
                self._md5 = hashlib.md5(fdno.read()).hexdigest()
        return self._md5

    def generate_path(self):
        """
        Returns the theoretical path that the artifact should be, instead of
        the current path it is.
        """
        return '{name}/{version}/{name}-{version}{extension}'.format(
            name=self.name,
            version=self.version,
            extension=self.extension,
        )

    def sign(self, key_path, passwd):
        """
        Defines how to sign this artifact, by default with detached signature
        """
        sign_detached(self.path, key=key_path, passphrase=passwd)

    def __str__(self):
        """
        This string uniquely identifies a artifact file, if two have the same
        string representation, the must point to the same file or a copy of
        it, if not, you wrongly generated two artifact with the same
        version/name and different content
        """
        return '%s(%s %s %s)' % (
            self.type, self.name, self.version, self.extension,
        )

    def __repr__(self):
        return self.__str__()


class ArtifactInode(list, object):
    """
    Simple list, abstracts a set of rpm instances
    """
    def __init__(self, inode):
        self.inode = inode
        super(ArtifactInode, self).__init__(self)

    def delete(self, noop=False):
        for artifact in self:
            if not noop and os.path.exists(artifact.path):
                os.remove(artifact.path)
            elif noop:
                logger.info('NOOP::%s would have been removed',
                            artifact.path)

    def get_artifacts(self, regmatch=None, fmatch=None):
        logger.debug('ArtifactInode::%s', self)
        arts = list(self)
        logger.debug('ArtifactInode::arts=%s', arts)
        logger.debug('ArtifactInode::fmatch=%s', fmatch)
        logger.debug('ArtifactInode::regmatch=%s', regmatch)
        if regmatch:
            arts = [art for art in self if regmatch.search(art.path)]
        elif fmatch:
            arts = [art for art in arts if fmatch(art)]
        logger.debug(
            'ArtifactInode::after filter arts=%s',
            arts,
        )
        return arts


class ArtifactVersion(dict, object):
    """Abstracts a set of artifacts inodes for a version"""
    def __init__(self, version, inode_class=ArtifactInode):
        self.version = version
        super(ArtifactVersion, self).__init__(self)
        self.inode_class = inode_class

    def __repr__(self):
        return "%s('%s')" % (self.__class__.__name__, self.version)

    def __eq__(self, other):
        return cmpfullver(self.version, other.version) == 0

    def __ne__(self, other):
        return cmpfullver(self.version, other.version) != 0

    def __lt__(self, other):
        return cmpfullver(self.version, other.version) < 0

    def __le__(self, other):
        return cmpfullver(self.version, other.version) <= 0

    def __gt__(self, other):
        return cmpfullver(self.version, other.version) > 0

    def __ge__(self, other):
        return cmpfullver(self.version, other.version) >= 0

    def add_artifact(self, artifact):
        if artifact.inode not in self:
            self[artifact.inode] = self.inode_class(artifact.inode)
        self[artifact.inode].append(artifact)
        return True

    def delete_inode(self, inode, noop=False):
        if inode in self:
            self[inode].delete(noop)
            self.pop(inode)

    def get_artifacts(self, regmatch=None, fmatch=None):
        arts = []
        logger.debug('ArtifactVersion::regmatch=%s', regmatch)
        logger.debug('ArtifactVersion::fmatch=%s', fmatch)
        for inode in self.itervalues():
            logger.debug(
                'ArtifactVersion::Iterating ArtifactInode %s',
                inode,
            )
            arts.extend(inode.get_artifacts(
                regmatch=regmatch,
                fmatch=fmatch
            ))
        return arts

    def delete(self, noop=False):
        for inode in self:
            self[inode].delete(noop)
            self.pop(inode)


class ArtifactName(dict, object):
    """Dict of available versions for an artifact name"""
    def __init__(self, name, version_class=ArtifactVersion):
        self.name = name
        super(ArtifactName, self).__init__(self)
        self.version_class = version_class

    def add_artifact(self, artifact, onlyifnewer):
        if onlyifnewer and (
            artifact.ver_rel in self or
            next(
                (
                    ver for ver in self.keys() if ver <= artifact.version
                ),
                None,
            )
        ):
            return False
        elif artifact.version not in self:
            self[artifact.version] = self.version_class(artifact.version)
        return self[artifact.version].add_artifact(artifact)

    def get_latest(self, num=1):
        """
        Returns the list of available inodes for the latest version
        if any
        """
        if not self:
            return None
        if not num:
            num = len(self)
        sorted_list = self.keys()
        sorted_list.sort(reverse=True)
        latest = {}
        if num > len(sorted_list):
            num = len(sorted_list)
        for pos in xrange(num):
            latest[sorted_list[pos]] = self.get(sorted_list[pos])
        return latest

    def delete_version(self, version, noop=False):
        if version in self:
            for inode in self[version].keys():
                self[version].delete_inode(inode, noop=noop)
            self.pop(version)

    def delete(self, noop=False):
        for version in self:
            for inode in self[version].keys():
                self[version].delete_inode(inode, noop=noop)
            self.pop(version)

    def get_artifacts(self, regmatch=None, fmatch=None, latest=0):
        arts = []
        logger.debug('ArtifactName::regmatch=%s', regmatch)
        logger.debug('ArtifactName::fmatch=%s', fmatch)
        logger.debug('ArtifactName::latest=%s', latest)
        if latest:
            versions = self.get_latest(num=latest).values()
        else:
            versions = self.values()
        for version in versions:
            logger.debug(
                'ArtifactName::Iterating ArtifactVersion %s',
                version,
            )
            arts.extend(version.get_artifacts(
                regmatch=regmatch,
                fmatch=fmatch
            ))
        return arts


class ArtifactList(dict, object):
    """
    Dict of artifacts, by name
    """
    def __init__(self, name, name_class=ArtifactName):
        self.name = name
        super(ArtifactList, self).__init__(self)
        self.name_class = name_class

    def add_pkg(self, artifact, onlyifnewer=False):
        if artifact.name is not None:
            if artifact.name not in self:
                self[artifact.name] = self.name_class(artifact.name)
            return self[artifact.name].add_artifact(artifact, onlyifnewer)

    def delete_version(self, art_name, art_version):
        """
        Removes the given artifact's version if it's in the list

        Args:
            art_name (str): Name of the artifact to remove it's version
            art_version (str): Version to remove

        Returns:
            None
        """
        if art_name in self:
            if art_version in self[art_name]:
                self[art_name].delete_version(art_version)
            if not self[art_name]:
                self.pop(art_name)

    def delete(self):
        """
        Deletes all the artifacts in this list
        """
        for name in self:
            for version in self[name].keys():
                self[name].delete_version(version)
            self.pop(name)

    def get_artifacts(self, regmatch=None, fmatch=None, latest=0):
        """
        Gets the list of artifacts, filtered or not.

        :param regmatch: Regular expression to filter the rpms path with
        :param fmatch: Filter function, must return True for packages to be
            included, or False to be excluded. The package object will be
            passed as parameter
        :param latest: number of latest versions to return (0 for all,)
        """
        arts = []
        logger.debug('ArtifactVersion::regmatch=%s', regmatch)
        logger.debug('ArtifactVersion::fmatch=%s', fmatch)
        logger.debug('ArtifactVersion::latest=%s', latest)
        for name in self.itervalues():
            logger.debug(
                'ArtifactList::Iterating ArtifactName %s',
                name,
            )
            arts.extend(name.get_artifacts(
                regmatch=regmatch,
                fmatch=fmatch,
                latest=latest,
            ))
        return arts
