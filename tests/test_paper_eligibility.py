import copy
import pytest
from trading_intelligence.catalog import strategy_library
from trading_intelligence.paper_eligibility import select_eligible


def manifest():
    library={x["id"]:x for x in strategy_library()}
    return {"mode":"isolated_qa","strategies":[{"strategy_id":i,"version":library[i]["version"],"definition_sha256":library[i]["definition_sha256"]} for i in ["143a732de079","2a7a1524c270"]]}


def test_exact_frozen_allowlist_uses_only_reviewed_definitions():
    selected=select_eligible(manifest(),isolated=True)
    assert [x["strategy_id"] for x in selected]==["143a732de079","2a7a1524c270"]


def test_qa_approval_cannot_activate_production():
    with pytest.raises(ValueError,match="approval"):
        select_eligible(manifest(),isolated=False)


@pytest.mark.parametrize("field,value",[("version",99999),("definition_sha256","0"*64)])
def test_changed_strategy_requires_new_review(field,value):
    changed=manifest();changed["strategies"][0][field]=value
    with pytest.raises(ValueError,match="changed"):
        select_eligible(changed,isolated=True)


def test_duplicate_strategy_not_counted_twice():
    duplicated=manifest();duplicated["strategies"].append(copy.deepcopy(duplicated["strategies"][0]))
    with pytest.raises(ValueError,match="Duplicate"):
        select_eligible(duplicated,isolated=True)
