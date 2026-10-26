from dataclasses import replace
import pytest
from tests.test_integrated_customizations import request,SEED
from backend.engine.calculator import _calculate_wall_check_once
from backend.engine.repository import JsonSeedRepository
from backend.engine.models import BoltInput,BoardLayer,StudInput

@pytest.mark.parametrize('design',['seismic','non_seismic'])
@pytest.mark.parametrize('pitch',[300.,450.,600.])
def test_bilateral_single_ply_uses_300_as_notice_standard(design,pitch):
    req=replace(request(1,1),design_case=design,bolt=BoltInput(3.5,340,(300.,300.,pitch),(2.,2.,1.)))
    result=_calculate_wall_check_once(req,JsonSeedRepository(SEED))
    notices=[n for n in result.notices if '피스 간격' in n]
    if pitch==300:
        assert not notices
    else:
        assert len(notices)==1 and '표준 간격 300 mm' in notices[0]

@pytest.mark.parametrize('rear,front',[(2,2),(1,2),(2,1),(1,3),(3,1),(0,1)])
def test_multi_ply_and_one_side_standard_remain_unchanged(rear,front):
    req=replace(request(rear,front),bolt=BoltInput(3.5,340,(300.,300.,600.),(2.,2.,1.)))
    result=_calculate_wall_check_once(req,JsonSeedRepository(SEED))
    assert not [n for n in result.notices if '피스 간격' in n]

def test_multi_ply_inner_300_still_reports_600_standard():
    req=replace(request(2,2),bolt=BoltInput(3.5,340,(300.,300.,300.),(2.,2.,1.)))
    result=_calculate_wall_check_once(req,JsonSeedRepository(SEED))
    assert any('표준 간격 600 mm' in n for n in result.notices)

@pytest.mark.parametrize('group,spec',[('CH-STUD','75CHS-08'),('I-STUD','I-STUD 102-08')])
def test_fixed_rear_single_front_300_does_not_warn(group,spec):
    req=replace(request(1,1),stud=StudInput(group,spec,'기본'),rear_boards=(BoardLayer('방화',25),),
                bolt=BoltInput(3.5,340,(300.,300.,300.),(2.,2.,1.)))
    result=_calculate_wall_check_once(req,JsonSeedRepository(SEED))
    assert not [n for n in result.notices if '피스 간격' in n]
