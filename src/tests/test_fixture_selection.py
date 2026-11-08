"""No-build skips must never turn a selected release build green."""
from types import SimpleNamespace
import pytest
import conftest


def request_for_build():
    return SimpleNamespace(module=SimpleNamespace(__name__='test_mix'))


def test_unselected_build_skips(monkeypatch):
    monkeypatch.delenv('MIX_NAME',raising=False)
    with pytest.raises(pytest.skip.Exception):
        conftest.selected_build.__wrapped__(request_for_build())


def test_selected_missing_build_fails(monkeypatch,tmp_path):
    monkeypatch.setenv('MIX_NAME','required-release')
    monkeypatch.setattr(conftest.checks,'SRC',str(tmp_path))
    monkeypatch.setattr(conftest.checks,'NAME','required-release')
    with pytest.raises(AssertionError,match='selected build meta missing'):
        conftest.selected_build.__wrapped__(request_for_build())
