
#    Copyright 2012 OpenStack Foundation
#    Copyright 2012-2013 Hewlett-Packard Development Company, L.P.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Utilities for consuming the version from pkg_resources.
"""

import itertools
import operator

import pkg_resources


def _is_int(string):
    try:
        int(string)
        return True
    except ValueError:
        return False


class SemanticVersion(object):
    """A pure semantic version independent of serialisation.

    See the pbr doc 'semver' for details on the semantics.
    """

    def __init__(self, major, minor=0, patch=0, prerelease_type=None,
                 prerelease=None, dev_count=None, githash=None):
        """Create a SemanticVersion.

        :param major: Major component of the version.
        :param minor: Minor component of the version. Defaults to 0.
        :param patch: Patch level component. Defaults to 0.
        :param prerelease_type: What sort of prerelease version this is -
            one of a(alpha), b(beta) or rc(release candidate).
        :param prerelease: For prerelease versions, what number prerelease.
            Defaults to 0.
        :param dev_count: How many commits since the last release.
        :param githash: What tree hash is this version for.

        :raises: ValueError if both a prerelease version and dev_count or
        githash are supplied. This is because semver (see the pbr semver
        documentation) does not permit both a prerelease version and a dev
        marker at the same time.
        """
        self._major = major
        self._minor = minor
        self._patch = patch
        self._prerelease_type = prerelease_type
        self._prerelease = prerelease
        if self._prerelease_type and not self._prerelease:
            self._prerelease = 0
        self._dev_count = dev_count
        self._githash = githash
        if prerelease_type is not None and dev_count is not None:
            raise ValueError(
                "invalid version: cannot have prerelease and dev strings %s %s"
                % (prerelease_type, dev_count))

    def __eq__(self, other):
        if not isinstance(other, SemanticVersion):
            return False
        return self.__dict__ == other.__dict__

    def __lt__(self, other):
        """Compare self and other, another Semantic Version."""
        # NB(lifeless) this could perhaps be rewritten as
        # lt (tuple_of_one, tuple_of_other) with a single check for
        # the typeerror corner cases - that would likely be faster
        # if this ever becomes performance sensitive.
        if not isinstance(other, SemanticVersion):
            raise TypeError("ordering to non-SemanticVersion is undefined")
        this_tuple = (self._major, self._minor, self._patch)
        other_tuple = (other._major, other._minor, other._patch)
        if this_tuple < other_tuple:
            return True
        elif this_tuple > other_tuple:
            return False
        if self._prerelease_type:
            if other._prerelease_type:
                # Use the a < b < rc cheat
                this_tuple = (self._prerelease_type, self._prerelease)
                other_tuple = (other._prerelease_type, other._prerelease)
                return this_tuple < other_tuple
            elif other._dev_count:
                raise TypeError(
                    "ordering pre-release with dev builds is undefined")
            else:
                return True
        elif self._dev_count:
            if other._dev_count:
                if self._dev_count < other._dev_count:
                    return True
                elif self._dev_count > other._dev_count:
                    return False
                elif self._githash == other._githash:
                    # == it not <
                    return False
                raise TypeError(
                    "same version with different hash has no defined order")
            elif other._prerelease_type:
                raise TypeError(
                    "ordering pre-release with dev builds is undefined")
            else:
                return True
        else:
            # This is not pre-release.
            # If the other is pre-release or dev, we are greater, which is ! <
            # If the other is not pre-release, we are equal, which is ! <
            return False

    def __le__(self, other):
        return self == other or self < other

    def __ge__(self, other):
        return not self < other

    def __gt__(self, other):
        return not self <= other

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return "pbr.version.SemanticVersion(%s)" % self.release_string()

    @classmethod
    def from_pip_string(klass, version_string):
        """Create a SemanticVersion from a version string.

        This method will parse a version like 1.3.0 into a SemanticVersion.

        For compatibility 1.3.0a1 versions are handled, though SemanticVersion
        will output them as 1.3.0.0a1 for PEP-440 compatability, and similarly
        pre-pbr-semver dev versions like 0.10.1.3.g83bef74 will be parsed but
        output as 0.10.1.dev3.g83bef74.
        """
        components = version_string.split('.')
        if len(components) < 3:
            components.extend([0] * (3 - len(components)))
        major = int(components[0])
        minor = int(components[1])
        dev_count = None
        prerelease_type = None
        prerelease = None
        githash = None

        def _parse_type(segment):
            # Discard leading digits (the 0 in 0a1)
            isdigit = operator.methodcaller('isdigit')
            segment = ''.join(itertools.dropwhile(isdigit, segment))
            isalpha = operator.methodcaller('isalpha')
            prerelease_type = ''.join(itertools.takewhile(isalpha, segment))
            prerelease = segment[len(prerelease_type)::]
            return prerelease_type, int(prerelease)
        if _is_int(components[2]):
            patch = int(components[2])
        else:
            # legacy version e.g. 1.2.0a1 (canonical is 1.2.0.0a1)
            # or 1.2.dev4.g1234 or 1.2.b4
            patch = 0
            components[2:2] = [0]
        remainder = components[3:]
        remainder_starts_with_int = False
        try:
            if remainder and int(remainder[0]):
                remainder_starts_with_int = True
        except ValueError:
            pass
        if remainder_starts_with_int:
            # old dev format - 0.1.2.3.g1234
            dev_count = int(remainder[0])
        else:
            if remainder and (remainder[0][0] == '0' or
                              remainder[0][0] in ('a', 'b', 'rc')):
                # Current RC/beta layout
                prerelease_type, prerelease = _parse_type(remainder[0])
                remainder = remainder[1:]
            if remainder:
                dev_count = int(remainder[0][3:])
        if len(remainder) > 1:
                githash = remainder[1][1:]
        return SemanticVersion(
            major, minor, patch, prerelease_type=prerelease_type,
            prerelease=prerelease, dev_count=dev_count, githash=githash)

    def brief_string(self):
        """Return the short version minus any alpha/beta tags."""
        return "%s.%s.%s" % (self._major, self._minor, self._patch)

    def debian_string(self):
        """Return the version number to use when building a debian package.

        This translates the PEP440/semver precedence rules into Debian version
        sorting operators.
        """
        return self._long_version("~", "+g")

    def decrement(self, minor=False, major=False):
        """Return a decremented SemanticVersion.

        Decrementing versions doesn't make a lot of sense - this method only
        exists to support rendering of pre-release versions strings into
        serialisations (such as rpm) with no sort-before operator.

        The 9999 magic version component is from the spec on this - pbr-semver.

        :return: A new SemanticVersion object.
        """
        if self._patch:
            new_patch = self._patch - 1
            new_minor = self._minor
            new_major = self._major
        else:
            new_patch = 9999
            if self._minor:
                new_minor = self._minor - 1
                new_major = self._major
            else:
                new_minor = 9999
                if self._major:
                    new_major = self._major - 1
                else:
                    new_major = 0
        return SemanticVersion(
            new_major, new_minor, new_patch)

    def increment(self, minor=False, major=False):
        """Return an incremented SemanticVersion.

        The default behaviour is to perform a patch level increment. When
        incrementing a prerelease version, the patch level is not changed
        - the prerelease serial is changed (e.g. beta 0 -> beta 1).

        Incrementing non-pre-release versions will not introduce pre-release
        versions - except when doing a patch incremental to a pre-release
        version the new version will only consist of major/minor/patch.

        :param minor: Increment the minor version.
        :param major: Increment the major version.
        :return: A new SemanticVersion object.
        """
        if self._prerelease_type:
            new_prerelease_type = self._prerelease_type
            new_prerelease = self._prerelease + 1
            new_patch = self._patch
        else:
            new_prerelease_type = None
            new_prerelease = None
            new_patch = self._patch + 1
        if minor:
            new_minor = self._minor + 1
            new_patch = 0
            new_prerelease_type = None
            new_prerelease = None
        else:
            new_minor = self._minor
        if major:
            new_major = self._major + 1
            new_minor = 0
            new_patch = 0
            new_prerelease_type = None
            new_prerelease = None
        else:
            new_major = self._major
        return SemanticVersion(
            new_major, new_minor, new_patch,
            new_prerelease_type, new_prerelease)

    def _long_version(self, pre_separator, hash_separator, rc_marker=""):
        """Construct a long string version of this semver.

        :param pre_separator: What separator to use between components
            that sort before rather than after. If None, use . and lower the
            version number of the component to preserve sorting. (Used for
            rpm support)
        :param hash_separator: What separator to use to append the git hash.
        """
        if ((self._prerelease_type or self._dev_count)
                and pre_separator is None):
            segments = [self.decrement().brief_string()]
            pre_separator = "."
        else:
            segments = [self.brief_string()]
        if self._prerelease_type:
            segments.append(
                "%s%s%s%s" % (pre_separator, rc_marker, self._prerelease_type,
                              self._prerelease))
        if self._dev_count:
            segments.append(pre_separator)
            segments.append('dev')
            segments.append(self._dev_count)
            if self._githash:
                segments.append(hash_separator)
                segments.append(self._githash)
        return "".join(str(s) for s in segments)

    def release_string(self):
        """Return the full version of the package.

        This including suffixes indicating VCS status.
        """
        return self._long_version(".", ".g", "0")

    def rpm_string(self):
        """Return the version number to use when building an RPM package.

        This translates the PEP440/semver precedence rules into RPM version
        sorting operators. Because RPM has no sort-before operator (such as the
        ~ operator in dpkg),  we show all prerelease versions as being versions
        of the release before.
        """
        return self._long_version(None, "+g")

    def to_dev(self, dev_count, githash):
        """Return a development version of this semver.

        :param dev_count: The number of commits since the last release.
        :param githash: The git hash of the tree with this version.
        """
        return SemanticVersion(
            self._major, self._minor, self._patch, dev_count=dev_count,
            githash=githash)

    def to_release(self):
        """Discard any pre-release or dev metadata.

        :return: A new SemanticVersion with major/minor/patch the same as this
            one.
        """
        return SemanticVersion(self._major, self._minor, self._patch)

    def version_tuple(self):
        """Present the version as a version_info tuple.

        For documentation on version_info tuples see the Python
        documentation for sys.version_info.

        Since semver and PEP-440 represent overlapping but not subsets of
        versions, we have to have some heuristic / mapping rules:
         - a/b/rc take precedence.
         - if there is no pre-release version the dev version is used.
         - serial is taken from the dev/a/b/c component.
         - final non-dev versions never get serials.
        """
        segments = [self._major, self._minor, self._patch]
        if self._prerelease_type:
            type_map = {'a': 'alpha',
                        'b': 'beta',
                        'rc': 'candidate',
                        }
            segments.append(type_map[self._prerelease_type])
            segments.append(self._prerelease)
        elif self._dev_count:
            segments.append('dev')
            segments.append(self._dev_count - 1)
        else:
            segments.append('final')
            segments.append(0)
        return tuple(segments)


class VersionInfo(object):

    def __init__(self, package):
        """Object that understands versioning for a package

        :param package: name of the python package, such as glance, or
                        python-glanceclient
        """
        self.package = package
        self.version = None
        self._cached_version = None
        self._semantic = None

    def __str__(self):
        """Make the VersionInfo object behave like a string."""
        return self.version_string()

    def __repr__(self):
        """Include the name."""
        return "pbr.version.VersionInfo(%s:%s)" % (
            self.package, self.version_string())

    def _get_version_from_pkg_resources(self):
        """Obtain a version from pkg_resources or setup-time logic if missing.

        This will try to get the version of the package from the pkg_resources
        record associated with the package, and if there is no such record
        falls back to the logic sdist would use.
        """
        try:
            requirement = pkg_resources.Requirement.parse(self.package)
            provider = pkg_resources.get_provider(requirement)
            result_string = provider.version
        except pkg_resources.DistributionNotFound:
            # The most likely cause for this is running tests in a tree
            # produced from a tarball where the package itself has not been
            # installed into anything. Revert to setup-time logic.
            from pbr import packaging
            result_string = packaging.get_version(self.package)
        return SemanticVersion.from_pip_string(result_string)

    def release_string(self):
        """Return the full version of the package.

        This including suffixes indicating VCS status.
        """
        return self.semantic_version().release_string()

    def semantic_version(self):
        """Return the SemanticVersion object for this version."""
        if self._semantic is None:
            self._semantic = self._get_version_from_pkg_resources()
        return self._semantic

    def version_string(self):
        """Return the short version minus any alpha/beta tags."""
        return self.semantic_version().brief_string()

    # Compatibility functions
    canonical_version_string = version_string
    version_string_with_vcs = release_string

    def cached_version_string(self, prefix=""):
        """Return a cached version string.

        This will return a cached version string if one is already cached,
        irrespective of prefix. If none is cached, one will be created with
        prefix and then cached and returned.
        """
        if not self._cached_version:
            self._cached_version = "%s%s" % (prefix,
                                             self.version_string())
        return self._cached_version
