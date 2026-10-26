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
    # 2026-10-26: 앵커 반력 지진항에 Ω0 적용 후 내진 앵커 기준 최대높이는 참조값(Ω0 적용 전)보다 낮다.
    # 내진은 경계 검증: 최대높이에서 통과, +50 mm에서 실패해야 한다.
    if case['design']=='seismic':
        request=WallCheckRequest(**data)
        height=result.anchor_max_height_mm
        assert 0<height<expected['with_runner_mm']
        def passes(h):
            r=_calculate_wall_check_once(replace(request,span_mm=h),JsonSeedRepository(ROOT/'data/seed'))
            return (r.stress_verdict==r.deflection_verdict==r.screw_tension_verdict=='O.K'
                    and r.intermediate['anchor_utilization']<=1.0)
        assert passes(height)
        assert not passes(height+50.0)
    else:
        assert result.anchor_max_height_mm==expected['with_runner_mm']
    assert result.eta==pytest.approx(expected['eta_3000'])
    assert result.I_eff_mm4==pytest.approx(expected['Ieff_3000'])
    assert result.Mn_kNm==pytest.approx(expected['Mn_3000'])

def test_latest_corrected_modulus_is_used():
    repo=JsonSeedRepository(ROOT/'data/seed')
    board=repo.get_board('고강도일반',12.5)
    assert board.E_GPa==6.06
    assert board.yield_ratio==.68
