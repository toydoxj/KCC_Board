"""Latest engine/material adoption plus explicitly retained custom conditions."""
from dataclasses import replace
import json
from pathlib import Path
import pytest
from backend.engine.calculator import _calculate_wall_check_once, calculate_wall_check
from backend.engine.models import BoardLayer, BoltInput, SeismicInput, StudInput, WallCheckRequest
from backend.engine.repository import JsonSeedRepository

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=json.loads((ROOT/'tests/golden/latest_github_reference.json').read_text(encoding='utf-8'))

@pytest.mark.parametrize('case',FIXTURES,ids=lambda c:c['name']+'_'+c['design'])
def test_unchanged_configurations_match_latest_github(case):
    data=case['input'].copy()
    data['rear_boards']=tuple(BoardLayer(**b) for b in data['rear_boards'])
    data['front_boards']=tuple(BoardLayer(**b) for b in data['front_boards'])
    data['stud']=StudInput(**data['stud'])
    data['bolt']=BoltInput(**data['bolt'])
    data['seismic']=SeismicInput(**data['seismic'])
    result=calculate_wall_check(WallCheckRequest(**data),JsonSeedRepository(ROOT/'data/seed'))
    expected=case['expected']
    assert result.max_height_mm==expected['without_runner_mm']
    assert result.anchor_max_height_mm==expected['with_runner_mm']
    assert result.eta==pytest.approx(expected['eta_3000'])
    assert result.I_eff_mm4==pytest.approx(expected['Ieff_3000'])
    assert result.Mn_kNm==pytest.approx(expected['Mn_3000'])

def test_latest_corrected_modulus_is_used():
    repo=JsonSeedRepository(ROOT/'data/seed')
    board=repo.get_board('고강도일반',12.5)
    assert board.E_GPa==6.06
    assert board.yield_ratio==.68
