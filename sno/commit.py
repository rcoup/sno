import click
import pygit2

from .core import check_git_user
from .diff import Diff
from .working_copy import WorkingCopy
from .structure import RepositoryStructure


@click.command()
@click.pass_context
@click.option("--message", "-m", help="Use the given message as the commit message.")
@click.option(
    "--allow-empty",
    is_flag=True, default=False,
    help=(
        "Usually recording a commit that has the exact same tree as its sole "
        "parent commit is a mistake, and the command prevents you from making "
        "such a commit. This option bypasses the safety"
    )
)
def commit(ctx, message, allow_empty):
    """ Record changes to the repository """
    repo_dir = ctx.obj["repo_dir"]
    repo = pygit2.Repository(repo_dir)
    if not repo:
        raise click.BadParameter("Not an existing repository", param_hint="--repo")

    check_git_user(repo)

    commit = repo.head.peel(pygit2.Commit)
    tree = commit.tree

    working_copy = WorkingCopy.open(repo)
    if not working_copy:
        raise click.UsageError("No working copy, use 'checkout'")

    working_copy.assert_db_tree_match(tree)

    rs = RepositoryStructure(repo)
    wcdiff = Diff(None)
    for i, dataset in enumerate(rs):
        wcdiff += working_copy.diff_db_to_tree(dataset)

    if not wcdiff and not allow_empty:
        raise click.ClickException("No changes to commit")

    new_commit = rs.commit(wcdiff, message, allow_empty=allow_empty)
