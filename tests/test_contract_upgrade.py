"""Version proposals preserve requirements, frozen inputs and negative controls."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from scene_acceptance.contract_upgrade import propose_upgrade, copy_replay_bundle
from scene_acceptance import evaluate
from scene_acceptance.model import sha, ContractError
from scene_acceptance.packs import default_registry

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'evaluation/packs-v1/fixtures'


def test_old_pin_is_rejected_until_explicit_upgrade(tmp_path):
    original = FIX / 'material_correct'
    before = {p.name:sha(p) for p in original.iterdir() if p.is_file()}
    old = evaluate('contract.json', 'scene.usda', bundle_root=original)
    assert old['verdict'] == 'EVALUATION_ERROR'
    copied = copy_replay_bundle(original, tmp_path / 'delivery')
    result = evaluate('contract.json', 'scene.usda', bundle_root=copied)
    assert result['verdict'] == 'ACCEPT_FOR_USE'
    changes = json.loads((copied / 'contract-upgrades.json').read_text())
    assert changes and changes[0]['requires_review']
    assert before == {p.name:sha(p) for p in original.iterdir() if p.is_file()}
    assert result['identity']['packs']['materials']['version'] == default_registry().get('materials').version


@pytest.mark.parametrize('fixture', ['pack_version_mismatch', 'pack_digest_mismatch'])
def test_upgrade_does_not_clear_deliberately_bad_pins(tmp_path, fixture):
    copied = copy_replay_bundle(FIX / fixture, tmp_path / 'delivery')
    result = evaluate('contract.json', 'scene.usda', bundle_root=copied)
    assert result['verdict'] == 'EVALUATION_ERROR'


def test_proposal_changes_only_known_versions_and_preserves_digest():
    contract = json.loads((FIX / 'material_correct/contract.json').read_text())
    contract['packs']['materials']['sha256'] = '0'*64
    before = deepcopy(contract)
    proposal, record = propose_upgrade(contract)
    expected = deepcopy(before)
    for item in record['changes']:
        expected['packs'][item['pack']]['version'] = item['after']
    assert proposal == expected
    assert contract == before
    assert proposal['packs']['materials']['sha256'] == '0'*64
    assert record['original_sha256'] != record['proposed_sha256']


def test_current_pin_has_no_proposed_change():
    original = json.loads((FIX / 'material_correct/contract.json').read_text())
    proposed, _ = propose_upgrade(original)
    again, record = propose_upgrade(proposed)
    assert proposed == again
    assert not record['changes'] and not record['requires_review']


def test_replay_copy_cannot_modify_source(tmp_path):
    source = tmp_path / 'source';source.mkdir()
    with pytest.raises(ContractError, match='separate'):
        copy_replay_bundle(source, source / 'nested')
    with pytest.raises(ContractError, match='separate'):
        copy_replay_bundle(source, source)


@pytest.mark.parametrize('packs', [None, [], {'materials':None}, {'materials':[]}])
def test_malformed_pack_declarations_remain_for_evaluator(tmp_path, packs):
    source = tmp_path/'source'; source.mkdir()
    value = json.loads((FIX/'material_correct/contract.json').read_text())
    value['packs'] = packs
    (source/'contract.json').write_text(json.dumps(value))
    before = (source/'contract.json').read_bytes()
    copied = copy_replay_bundle(source,tmp_path/'copy')
    assert (copied/'contract.json').read_bytes() == before
    assert (source/'contract.json').read_bytes() == before
