"""Scientific checks run on the user's frozen worker, never during packaging."""
import copy
import json
import math

import pytest

from completion.physics import area_ratio, exit_mach, mass_flow, state, thrust, verification
from completion.protocol import FAMILIES, key, load_data, messages, schedule
from completion.scoring import decode, evaluate


def answer(value=3000, unit="N", **changes):
    result = dict(decision="answer", value=value, unit=unit, issue="none",
                  evidence_ids=[], assumptions=["supplied exit state"], explanation="Momentum plus pressure thrust")
    result.update(changes)
    return json.dumps(result)


def thrust_case():
    return {"reference":{"kind":"thrust", "inputs":dict(mdot=2,Ve=1000,pe=200000,pa=100000,Ae=.01),
                         "decision":"answer", "issue":"none", "atol":1e-6, "relevant_ids":["N01"]}}


def test_exact_mach_two_identity():
    assert area_ratio(2, 1.4)==pytest.approx(1.6875, abs=1e-13)
    assert exit_mach(1.6875, 1.4)==pytest.approx(2, abs=1e-12)
    result=state(1e6,900,.001,1.4,287,1.6875,1e5)
    assert result["Te"]==pytest.approx(500)
    assert result["Ve"]==pytest.approx(2*math.sqrt(1.4*287*500))
    assert result["F"]==pytest.approx(result["momentum_thrust"]+result["pressure_thrust"])


def test_independent_reference_grid():
    assert len(verification()["independent_root_checks"])==35


@pytest.mark.parametrize("epsilon", [1.0001,1.2,2,10,50])
@pytest.mark.parametrize("gamma", [1.2,1.4,1.67])
def test_supersonic_root_and_continuity(epsilon,gamma):
    result=state(2e6,1800,.0005,gamma,300,epsilon,1e5)
    assert result["Me"]>1
    assert area_ratio(result["Me"],gamma)==pytest.approx(epsilon, rel=1e-12)
    assert result["continuity_relative_error"]<1e-10


def test_mass_flow_scaling():
    baseline=mass_flow(1e6,900,.001,1.4,287)
    assert mass_flow(2e6,900,.001,1.4,287)==pytest.approx(2*baseline)
    assert mass_flow(1e6,3600,.001,1.4,287)==pytest.approx(baseline/2)
    assert mass_flow(1e6,900,.003,1.4,287)==pytest.approx(3*baseline)


def test_pressure_term_and_ambient_effect():
    assert thrust(2,1000,200000,100000,.01)==3000
    assert thrust(2,1000,200000,300000,.01)==1000


@pytest.mark.parametrize("operation", [lambda:exit_mach(.9,1.4),lambda:exit_mach(2,1),
    lambda:mass_flow(-1,900,.001,1.4,287),lambda:mass_flow(1e6,0,.001,1.4,287),
    lambda:area_ratio(float("nan"),1.4),lambda:thrust(2,1000,100000,-1,.01)])
def test_invalid_physical_inputs(operation):
    with pytest.raises(ValueError):
        operation()


def test_units_conversion_and_tolerance():
    case=thrust_case()
    assert evaluate(case,answer(3,"kN"),[])["correct"]
    assert evaluate(case,answer(3029,"N"),[])["correct"]
    assert not evaluate(case,answer(3031,"N"),[])["correct"]
    assert not evaluate(case,answer(3000,"kg/s"),[])["correct"]
    assert not evaluate(case,answer(3,"N"),[])["correct"]


@pytest.mark.parametrize("text", ["", "```json\n{}\n```", "{}", "[]", "3000 N",
    '{"decision":"answer","decision":"abstain"}',
    answer(True),answer(float("nan")),answer(float("inf")),answer(3000,"")])
def test_malformed_or_nonfinite_is_incorrect(text):
    assert decode(text) is None
    assert not evaluate(thrust_case(),text,[])["correct"]


def test_abstention_requires_decision_and_issue():
    cases,_,_=load_data()
    case=next(c for c in cases if c["family"]=="missing_inputs")
    text=answer(None,None,decision="abstain",issue="missing_inputs")
    assert evaluate(case,text,[])["correct"]
    assert not evaluate(case,answer(None,None,decision="abstain",issue="internal_shock"),[])["correct"]
    assert not evaluate(case,answer(3000),[])["correct"]


def test_citation_ids_are_separate_from_numeric_score():
    result=evaluate(thrust_case(),answer(evidence_ids=["invented"]),[{"id":"N01"}])
    assert result["correct"]
    assert result["citation_id_precision"]==0
    assert result["retrieved_reference_recall"]==1


def test_benchmark_split_and_schedule():
    cases,_,protocol=load_data()
    assert len(cases)==48
    assert len({c["id"] for c in cases})==48
    for family in FAMILIES:
        assert sum(c["family"]==family and c["split"]=="development" for c in cases)==2
        assert sum(c["family"]==family and c["split"]=="evaluation" for c in cases)==6
    full=schedule(cases,"full",protocol)
    assert len(full)==216
    assert len({key(x) for x in full})==216
    assert full==schedule(cases,"full",protocol)
    assert len(schedule(cases,"presentation",protocol))==12
    dev={c["id"] for c in cases if c["split"]=="development"}
    assert not dev & {x["case_id"] for x in full}


def test_reference_metadata_cannot_leak_into_prompt():
    cases,corpus,_=load_data()
    original=cases[0]
    changed=copy.deepcopy(original)
    changed["reference"]={"value":"SECRET_GOLD_9ff", "issue":"SECRET_LABEL"}
    assert messages(original,corpus[:3])==messages(changed,corpus[:3])
    assert "SECRET_GOLD_9ff" not in json.dumps(messages(changed,corpus[:3]))


def test_bm25_actually_returns_three_sourced_passages():
    from completion.protocol import Retriever
    _,corpus,_=load_data()
    results=Retriever(corpus).get("thrust mass flow exit velocity pressure area")
    assert len(results)==3
    assert len({p["id"] for p in results})==3
    assert all(p["source"].startswith("https://") for p in results)
