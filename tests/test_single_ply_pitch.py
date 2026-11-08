from dataclasses import replace
import pytest
from tests.test_integrated_customizations import request,SEED
from backend.engine.calculator import _build_section,_calculate_wall_check_once,_connection_capacity_kN,_layer_pitch_count
from backend.engine.constants import ONE_SIDED_SINGLE_PLY_SCREW_COUNT
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

@pytest.mark.parametrize('rear,front',[(2,2),(1,2),(2,1),(1,3),(3,1),(0,2),(0,3)])
def test_multi_ply_and_one_side_multi_standard_remain_unchanged(rear,front):
    req=replace(request(rear,front),bolt=BoltInput(3.5,340,(300.,300.,600.),(2.,2.,1.)))
    result=_calculate_wall_check_once(req,JsonSeedRepository(SEED))
    assert not [n for n in result.notices if '피스 간격' in n]

# 2026-11-08 사용자 결정: 일면마감 1P 단독 구성은 1P 간격 표준 300 mm, 피치당 피스 2개
@pytest.mark.parametrize('rear,front',[(0,1),(1,0)])
@pytest.mark.parametrize('pitch',[300.,600.])
def test_one_sided_single_ply_uses_300_standard_and_two_screws(rear,front,pitch):
    req=replace(request(rear,front),bolt=BoltInput(3.5,340,(300.,300.,pitch),(2.,2.,1.)))
    section=_build_section(req,JsonSeedRepository(SEED))
    board=next(layer for layer in section.layers if layer.layer_type=='board')
    assert _layer_pitch_count(board,req.bolt)==(pitch,ONE_SIDED_SINGLE_PLY_SCREW_COUNT)
    result=_calculate_wall_check_once(req,JsonSeedRepository(SEED))
    notices=[n for n in result.notices if '피스 간격' in n]
    if pitch==300:
        assert not notices
    else:
        assert len(notices)==1 and '표준 간격 300 mm' in notices[0]

def test_one_sided_single_ply_doubles_connection_capacity():
    req=replace(request(0,1),bolt=BoltInput(3.5,340,(300.,300.,300.),(2.,2.,1.)))
    repo=JsonSeedRepository(SEED)
    section=_build_section(req,repo)
    board=next(layer for layer in section.layers if layer.layer_type=='board')
    kwargs=dict(stud_thickness_mm=section.stud_section.t,stud_tensile_strength=400.)
    new=_connection_capacity_kN(board,req.bolt,req.span_mm,**kwargs)
    old=_connection_capacity_kN(replace(board,connection_count=None),req.bolt,req.span_mm,**kwargs)
    assert new==pytest.approx(2.*old)

def test_bilateral_single_ply_keeps_one_screw():
    req=replace(request(1,1),bolt=BoltInput(3.5,340,(300.,300.,300.),(2.,2.,1.)))
    section=_build_section(req,JsonSeedRepository(SEED))
    for layer in section.layers:
        if layer.layer_type=='board':
            assert _layer_pitch_count(layer,req.bolt)==(300.,1.)

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
