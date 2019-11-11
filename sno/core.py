import os

import pygit2
from click import ClickException
from osgeo import gdal, ogr, osr  # noqa


gdal.UseExceptions()


def walk_tree(top, path='', topdown=True):
    """
    Corollary of os.walk() for git Tree objects:

    For each subtree in the tree rooted at top (including top itself),
    yields a 4-tuple:
        top_tree, top_path, subtree_names, blob_names

    top_tree is a Tree object
    top_path is a string, the path to top_tree with respect to the root path.
    subtree_names is a list of names for the subtrees in top_tree
    blob_names is a list of names for the blobs in top_tree.

    To get a full path (which begins with top_path) to a blob or subtree in
    top_path, do `os.path.join(top_path, name)`.

    To get a TreeEntry object, do `top_tree / name`
    To get a Blob or Tree object, do `(top_tree / name).obj`

    If optional arg `topdown` is true or not specified, the tuple for a
    subtree is generated before the tuples for any of its subtrees
    (pre-order traversal).  If topdown is false, the tuple
    for a subtree is generated after the tuples for all of its
    subtrees (post-order traversal).

    When topdown is true, the caller can modify the subtree_names list in-place
    (e.g., via del or slice assignment), and walk will only recurse into the
    subtrees whose names remain; this can be used to prune the
    search, or to impose a specific order of visiting.  Modifying subtree_names when
    topdown is false is ineffective, since the directories in subtree_names have
    already been generated by the time subtree_names itself is generated. No matter
    the value of topdown, the list of subtrees is retrieved before the
    tuples for the tree and its subtrees are generated.
    """
    subtree_names = []
    blob_names = []

    for entry in top:
        is_tree = (entry.type == 'tree')

        if is_tree:
            subtree_names.append(entry.name)
        elif entry.type == 'blob':
            blob_names.append(entry.name)
        else:
            pass

    if topdown:
        yield top, path, subtree_names, blob_names
        for name in subtree_names:
            subtree_path = os.path.join(path, name)
            subtree = (top / name).obj
            yield from walk_tree(subtree, subtree_path, topdown=topdown)
    else:
        for name in subtree_names:
            subtree_path = os.path.join(path, name)
            subtree = (top / name).obj
            yield from walk_tree(subtree, subtree_path, topdown=topdown)
        yield top, path, subtree_names, blob_names


def check_git_user(repo=None):
    """
    Checks whether a user is defined in either the repo configuration or globally

    If not, errors with a semi-helpful message
    """
    if repo:
        cfg = repo.config
    else:
        try:
            cfg = pygit2.Config.get_global_config()
        except IOError:
            # there is no global config
            cfg = {}

    try:
        user_email = cfg['user.email']
        user_name = cfg['user.name']
        if user_email and user_name:
            return (user_email, user_name)
    except KeyError:
        pass

    msg = [
        'Please tell me who you are.',
        '\nRun',
        '\n  git config --global user.email "you@example.com"',
        '  git config --global user.name "Your Name"',
        '\nto set your account\'s default identity.',
    ]
    if repo:
        msg.append('Omit --global to set the identity only in this repository.')

    msg.append('\n(sno uses the same credentials and configuration as git)')

    raise ClickException("\n".join(msg))
