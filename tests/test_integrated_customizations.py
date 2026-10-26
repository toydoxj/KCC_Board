"""User-approved integration: asymmetric fasteners and catalog restrictions."""
from dataclasses import replace
from pathlib import Path

import pytest

from backend.engine.calculator import _build_section, _calculate_wall_check_once, _layer_pitch_count, _shear_connection_by_layer
from backend.engine.models import BoardLayer, BoltInput, SeismicInput, StudInput, WallCheckRequest
from backend.engine.repository import JsonSeedRepository, RepositoryLookupError

SEED = Path(__file__).resolve().parents[1] / "data/seed"

def request(rear=1, front=2):
    return WallCheckRequest(
        rear_boards=tuple(BoardLayer("일반",12.5) for _ in range(rear)),
        front_boards=tuple(BoardLayer("일반",12.5) for _ in range(front)),
        stud=StudInput("C-STUD","100S-45-08","기본"),
        horizontal_load_kg_m2=0.25*1000/9.81,live_load_kN_m2=0.25,
        vertical_load_kN_m=0,spacing_mm=450,span_mm=3000,deflection_limit_denom=240,
        bolt=BoltInput(3.5,340,(900.,300.,600.),(3.,2.,1.)),
        seismic=SeismicInput(.22,1.5,Fa=1.3),design_case="non_seismic",
    )

@pytest.mark.parametrize("rear,front,expected",[(1,2,2),(2,1,2),(1,3,3),(3,1,3),(1,1,1)])
def test_single_face_uses_active_finishing_row_in_all_connection_paths(rear,front,expected):
    repo=JsonSeedRepository(SEED);req=request(rear,front);section=_build_section(req,repo)
    index=0 if rear==1 else rear+1
    layer=section.layers[index]
    assert layer.connection_order == expected
    target_pitch=(600.,300.,900.)[expected-1]
    target_count=1.
    assert _layer_pitch_count(layer,req.bolt)==(target_pitch,target_count)
    # Resolve the same physical layer explicitly. Both eta and Mn paths must agree.
    explicit=replace(section,layers=tuple(replace(x,order=expected,connection_order=None) if x is layer else x for x in section.layers))
    for strength in (False,True):
        assert _shear_connection_by_layer(section,req,for_strength=strength)==_shear_connection_by_layer(explicit,req,for_strength=strength)
    result=_calculate_wall_check_once(req,repo)
    face_pitches=[300.,600.] if max(rear,front)==2 else [target_pitch]
    assert result.intermediate["screw_tension_spacing_mm"] == max(face_pitches+[target_pitch])


@pytest.mark.parametrize("rear,front",[(1,2),(2,1),(1,3),(3,1)])
@pytest.mark.parametrize("pitch",[300.,450.,600.,375.])
@pytest.mark.parametrize("design",["non_seismic","seismic"])
def test_asymmetric_single_ply_keeps_count_and_only_follows_finish_pitch(rear,front,pitch,design):
    from backend.engine.calculator import _connection_capacity_kN
    repo=JsonSeedRepository(SEED)
    finish_order=max(rear,front)
    pitches=(900.,pitch,600.) if finish_order==2 else (pitch,300.,600.)
    req=replace(request(rear,front),design_case=design,
                bolt=BoltInput(3.5,340,pitches,(3.,2.,1.)))
    section=_build_section(req,repo)
    index=0 if rear==1 else rear+1
    single=section.layers[index]
    assert _layer_pitch_count(single,req.bolt)==(pitch,1.)
    # The multi-ply face keeps all original pitch/count inputs.
    other=[layer for i,layer in enumerate(section.layers) if i!=index and layer.layer_type=='board']
    expected=[(600.,1.),(pitch,2.)] if finish_order==2 else [(600.,1.),(300.,2.),(pitch,3.)]
    assert sorted(_layer_pitch_count(layer,req.bolt) for layer in other)==sorted(expected)
    previous=replace(single,connection_count=None)
    for strength in (False,True):
        kwargs=dict(stud_thickness_mm=section.stud_section.t,stud_tensile_strength=400.,for_strength=strength)
        new=_connection_capacity_kN(single,req.bolt,req.span_mm,**kwargs)
        old=_connection_capacity_kN(previous,req.bolt,req.span_mm,**kwargs)
        assert new==pytest.approx(old/finish_order)
    _calculate_wall_check_once(req,repo)

def test_fixed_ch_rear_keeps_latest_300mm_two_screws():
    repo=JsonSeedRepository(SEED)
    req=replace(request(),stud=StudInput("CH-STUD","75CHS-08","기본"),rear_boards=(BoardLayer("방화",25),))
    section=_build_section(req,repo)
    assert _layer_pitch_count(section.layers[0],req.bolt)==(300.,2.)
    assert section.layers[0].connection_order is None

@pytest.mark.parametrize("kind,t",[("차음",9.5),("차음",15),("전방수",15)])
def test_removed_boards_are_not_available(kind,t):
    repo=JsonSeedRepository(SEED)
    assert (kind,t) not in {(b.kind,b.thickness) for b in repo.list_board_catalog()}
    with pytest.raises(RepositoryLookupError):repo.get_board(kind,t)

def test_i_stud_one_side_is_rejected_even_with_a_valid_rear_board():
    repo=JsonSeedRepository(SEED)
    stud=next(s for s in repo.list_studs() if s.group=="I-STUD")
    req=replace(request(),stud=StudInput("I-STUD",stud.name,"일면마감"),rear_boards=(BoardLayer("방화",25),))
    with pytest.raises(ValueError,match="일면마감은 지원하지"):_build_section(req,repo)

@pytest.mark.parametrize("kind,t",[("일반",12.5),("방수",9.5),("방화",19),("고강도일반",15)])
def test_i_stud_selected_rear_board_drives_properties_and_connection(kind,t):
    repo=JsonSeedRepository(SEED)
    req=replace(request(),stud=StudInput("I-STUD","I-STUD 102-08","기본"),rear_boards=(BoardLayer(kind,t),))
    section=_build_section(req,repo)
    rear=section.layers[0]
    assert rear.board_property == repo.get_board(kind,t)
    assert rear.thickness_mm == t
    assert _layer_pitch_count(rear,req.bolt)==(300.,2.)
    assert section.stud_layer.y_centroid_mm==section.stud_section.cy
    result=_calculate_wall_check_once(req,repo)
    assert result.layers[0].axial_strength_kN==pytest.approx(repo.get_board(kind,t).Fy*req.spacing_mm*t/1000)

@pytest.mark.parametrize("count",[0,2])
def test_i_stud_keeps_one_inserted_rear_board(count):
    repo=JsonSeedRepository(SEED)
    req=replace(request(),stud=StudInput("I-STUD","I-STUD 102-08","기본"),rear_boards=tuple(BoardLayer("일반",12.5) for _ in range(count)))
    with pytest.raises(ValueError,match="후면 석고보드 1장"):_build_section(req,repo)
