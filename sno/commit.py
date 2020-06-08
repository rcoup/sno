import re

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
import pygit2

from .core import check_git_user
from .diff import Diff
from .exceptions import NotFound, NO_CHANGES, NO_DATA, NO_WORKING_COPY
from .output_util import dump_json_output
from .repo_files import (
    COMMIT_EDITMSG,
    write_repo_file,
    read_repo_file,
    user_edit_repo_file,
)
from .status import (
    get_branch_status_message,
    get_diff_status_message,
    get_diff_status_json,
    diff_status_to_text,
)
from .timestamps import (
    datetime_to_iso8601_utc,
    timedelta_to_iso8601_tz,
    commit_time_to_text,
)
from .working_copy import WorkingCopy
from .structure import RepositoryStructure
from .cli_util import MutexOption, do_json_option


@click.command()
@click.pass_context
@click.option(
    "--message",
    "-m",
    multiple=True,
    help="Use the given message as the commit message. If multiple `-m` options are given, their values are concatenated as separate paragraphs.",
    cls=MutexOption,
    exclusive_with=["message_file"],
)
@click.option(
    "message_file",
    "--file",
    "-F",
    type=click.File(encoding="utf-8"),
    help="Take the commit message from the given file. Use `-` to read the message from the standard input.",
    cls=MutexOption,
    exclusive_with=["message"],
)
@click.option(
    "--allow-empty",
    is_flag=True,
    default=False,
    help=(
        "Usually recording a commit that has the exact same tree as its sole "
        "parent commit is a mistake, and the command prevents you from making "
        "such a commit. This option bypasses the safety"
    ),
)
@do_json_option
def commit(ctx, message, message_file, allow_empty, do_json):
    """ Record changes to the repository """
    repo = ctx.obj.repo

    if repo.is_empty:
        raise NotFound(
            'Empty repository.\n  (use "sno import" to add some data)',
            exit_code=NO_DATA,
        )

    check_git_user(repo)

    commit = repo.head.peel(pygit2.Commit)
    tree = commit.tree

    working_copy = WorkingCopy.open(repo)
    if not working_copy:
        raise NotFound("No working copy, use 'checkout'", exit_code=NO_WORKING_COPY)

    working_copy.assert_db_tree_match(tree)

    rs = RepositoryStructure(repo)
    wc_diff = working_copy.diff_to_tree(rs)

    if not wc_diff and not allow_empty:
        raise NotFound("No changes to commit", exit_code=NO_CHANGES)

    if message_file:
        commit_msg = message_file.read().strip()
    elif message:
        commit_msg = "\n\n".join([m.strip() for m in message]).strip()
    else:
        commit_msg = get_commit_message(repo, wc_diff, quiet=do_json)

    if not commit_msg:
        raise click.UsageError("No commit message")

    rs.commit(wc_diff, commit_msg, allow_empty=allow_empty)

    new_commit = repo.head.peel(pygit2.Commit)
    jdict = commit_obj_to_json(new_commit, repo, wc_diff)
    if do_json:
        dump_json_output(jdict, sys.stdout)
    else:
        click.echo(commit_json_to_text(jdict))


def get_commit_message(repo, diff, draft_message="", quiet=False):
    """ Launches the system editor to get a commit message """
    initial_message = [
        draft_message,
        "# Please enter the commit message for your changes. Lines starting",
        "# with '#' will be ignored, and an empty message aborts the commit.",
        "#",
        re.sub(r"^", "# ", get_branch_status_message(repo), flags=re.MULTILINE),
        "#",
        "# Changes to be committed:",
        "#",
        re.sub(
            r"^",
            "# ",
            (get_diff_status_message(diff) or "  No changes (empty commit)"),
            flags=re.MULTILINE,
        ),
        "#",
    ]

    write_repo_file(repo, COMMIT_EDITMSG, "\n".join(initial_message) + "\n")
    if not quiet:
        click.echo("hint: Waiting for your editor to close the file...")
    user_edit_repo_file(repo, COMMIT_EDITMSG)
    message = read_repo_file(repo, COMMIT_EDITMSG)

    # strip:
    # - whitespace at start/end
    # - comment lines
    # - blank lines surrounding comment lines
    message = re.sub(r"^\n*#.*\n", "", message, flags=re.MULTILINE)
    return message.strip()


def commit_obj_to_json(commit, repo, wc_diff):
    branch = None
    if not repo.head_is_detached:
        branch = repo.branches[repo.head.shorthand].shorthand
    commit_time = datetime.fromtimestamp(commit.commit_time, timezone.utc)
    commit_time_offset = timedelta(minutes=commit.commit_time_offset)
    return {
        "sno.commit/v1": {
            "commit": commit.id.hex,
            "abbrevCommit": commit.short_id,
            "author": commit.author.email,
            "committer": commit.committer.email,
            "branch": branch,
            "message": commit.message,
            "changes": get_diff_status_json(wc_diff),
            "commitTime": datetime_to_iso8601_utc(commit_time),
            "commitTimeOffset": timedelta_to_iso8601_tz(commit_time_offset),
        }
    }


def commit_json_to_text(jdict):
    jdict = jdict["sno.commit/v1"]
    branch = jdict["branch"]
    commit = jdict["abbrevCommit"]
    message = jdict["message"].replace("\n", " ")
    diff = diff_status_to_text(jdict["changes"])
    datetime = commit_time_to_text(jdict["commitTime"], jdict["commitTimeOffset"])
    return f"[{branch} {commit}] {message}\n{diff}\n  Date: {datetime}"
