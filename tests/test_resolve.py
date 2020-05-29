import json
import pytest

from sno.diff_output import json_row
from sno.exceptions import INVALID_OPERATION
from sno.merge_util import MergeIndex
from sno.repo_files import RepoState, write_repo_file
from sno.structure import RepositoryStructure


H = pytest.helpers.helpers()


def get_conflict_ids(cli_runner):
    r = cli_runner.invoke(["conflicts", "-s", "--flat", "--json"])
    assert r.exit_code == 0, r
    return json.loads(r.stdout)["sno.conflicts/v1"]


def delete_remaining_conflicts(cli_runner):
    # TODO - do this with a single resolve when this is supported.
    conflict_ids = get_conflict_ids(cli_runner)
    while conflict_ids:
        r = cli_runner.invoke(["resolve", conflict_ids[0], "--with=delete"])
        assert r.exit_code == 0, r
        conflict_ids = get_conflict_ids(cli_runner)


def get_json_feature(rs, layer, pk):
    try:
        _, feature = rs[layer].get_feature(pk, ogr_geoms=False)
        return json_row(feature, H.POLYGONS.LAYER_PK)
    except KeyError:
        return None


def test_resolve_with_version(create_conflicts, cli_runner):
    with create_conflicts(H.POLYGONS) as repo:
        r = cli_runner.invoke(["merge", "theirs_branch", "--json"])
        assert r.exit_code == 0, r
        assert json.loads(r.stdout)["sno.merge/v1"]["conflicts"]
        assert RepoState.get_state(repo) == RepoState.MERGING

        # Can't just complete the merge until we resolve the conflicts.
        r = cli_runner.invoke(["merge", "--continue"])
        assert r.exit_code == INVALID_OPERATION

        conflict_ids = get_conflict_ids(cli_runner)
        resolutions = iter(["ancestor", "ours", "theirs", "delete"])

        # Keep track of which order we resolve the conflicts - each conflict
        # resolved will have a primary key, and we resolve conflicts in
        # primary key order, but the primary keys are not contiguous.
        pk_order = []
        # Each conflict also has an internal "conflict" key - just its index
        # in the original list of conflicts - these are contiguous, but
        # we don't necessarily resolve the conflicts in this order.
        ck_order = []

        while conflict_ids:
            num_conflicts = len(conflict_ids)
            conflict_id = conflict_ids[0]
            pk = conflict_id.split("=", 1)[1]
            pk_order += [pk]

            r = cli_runner.invoke(
                ["resolve", conflict_id, f"--with={next(resolutions)}"]
            )
            assert r.exit_code == 0, r
            conflict_ids = get_conflict_ids(cli_runner)
            assert len(conflict_ids) == num_conflicts - 1

            resolved_keys = MergeIndex.read_from_repo(repo).resolves.keys()
            ck_order += [k for k in resolved_keys if k not in ck_order]

        assert len(conflict_ids) == 0

        merge_index = MergeIndex.read_from_repo(repo)
        assert len(merge_index.entries) == 242
        assert len(merge_index.conflicts) == 4
        assert len(merge_index.resolves) == 4

        ck0, ck1, ck2, ck3 = ck_order
        # Conflict ck0 is resolved to ancestor, but the ancestor is None.
        assert merge_index.resolves[ck0] == []
        assert merge_index.conflicts[ck0].ancestor is None
        assert merge_index.resolves[ck1] == [merge_index.conflicts[ck1].ours]
        assert merge_index.resolves[ck2] == [merge_index.conflicts[ck2].theirs]
        assert merge_index.resolves[ck3] == []

        r = cli_runner.invoke(["merge", "--continue"])
        assert r.exit_code == 0, r
        assert RepoState.get_state(repo) != RepoState.MERGING

        merged = RepositoryStructure.lookup(repo, "HEAD")
        ours = RepositoryStructure.lookup(repo, "ours_branch")
        theirs = RepositoryStructure.lookup(repo, "theirs_branch")
        l = H.POLYGONS.LAYER

        pk0, pk1, pk2, pk3 = pk_order
        # Feature at pk0 was resolved to ancestor, which was None.
        assert get_json_feature(merged, l, pk0) is None
        assert get_json_feature(merged, l, pk1) == get_json_feature(ours, l, pk1)
        assert get_json_feature(merged, l, pk2) == get_json_feature(theirs, l, pk2)
        assert get_json_feature(merged, l, pk3) is None


def test_resolve_with_file(create_conflicts, cli_runner):
    with create_conflicts(H.POLYGONS) as repo:
        r = cli_runner.invoke(["diff", "ancestor_branch..ours_branch", "--geojson"])
        assert r.exit_code == 0, r
        ours_geojson = json.loads(r.stdout)["features"][0]
        assert ours_geojson["id"] == "I::98001"

        r = cli_runner.invoke(["diff", "ancestor_branch..theirs_branch", "--geojson"])
        assert r.exit_code == 0, r
        theirs_geojson = json.loads(r.stdout)["features"][0]
        assert theirs_geojson["id"] == "I::98001"

        r = cli_runner.invoke(["merge", "theirs_branch", "--json"])
        assert r.exit_code == 0, r
        assert json.loads(r.stdout)["sno.merge/v1"]["conflicts"]

        r = cli_runner.invoke(["conflicts", "-s", "--json"])
        assert r.exit_code == 0, r

        conflicts = json.loads(r.stdout)["sno.conflicts/v1"]
        add_add_conflict = conflicts[H.POLYGONS.LAYER]["featureConflicts"]["add/add"][0]
        assert add_add_conflict == "nz_waca_adjustments:id=98001"

        # These IDs are irrelevant, but we change them to at least be unique.
        ours_geojson["id"] = "ours-feature"
        theirs_geojson["id"] = "theirs-feature"
        # Changing this ID means the two features no long conflict.
        theirs_geojson["properties"]["id"] = 98002

        resolution = {
            'features': [ours_geojson, theirs_geojson],
            'type': 'FeatureCollection',
        }
        write_repo_file(repo, "resolution.geojson", json.dumps(resolution))
        r = cli_runner.invoke(
            ["resolve", add_add_conflict, "--with-file=resolution.geojson"]
        )
        assert r.exit_code == 0, r

        merge_index = MergeIndex.read_from_repo(repo)
        assert len(merge_index.entries) == 242
        assert len(merge_index.conflicts) == 4
        assert len(merge_index.resolves) == 1

        ck = next(iter(merge_index.resolves.keys()))
        assert len(merge_index.resolves[ck]) == 2  # Resolved with 2 features

        delete_remaining_conflicts(cli_runner)

        r = cli_runner.invoke(["merge", "--continue"])
        assert r.exit_code == 0, r

        merged = RepositoryStructure.lookup(repo, "HEAD")
        ours = RepositoryStructure.lookup(repo, "ours_branch")
        theirs = RepositoryStructure.lookup(repo, "theirs_branch")
        l = H.POLYGONS.LAYER

        # Both features are present in the merged repo, ours at 98001 and theirs at 98002.
        assert get_json_feature(merged, l, 98001) == get_json_feature(ours, l, 98001)
        # Theirs feature is slightly different - it has a new primary key.
        assert get_json_feature(merged, l, 98002) != get_json_feature(theirs, l, 98001)

        modified_theirs_json = get_json_feature(theirs, l, 98001)
        modified_theirs_json["id"] = 98002
        modified_theirs_json["properties"]["id"] = 98002
        assert get_json_feature(merged, l, 98002) == modified_theirs_json