import sys
from importlib.metadata import version

import pytest

from tradurre.__main__ import main


def test_version_flag(monkeypatch, capsys):
    # start-tradurre.bat parses the second token of this line to decide whether to upgrade.
    monkeypatch.setattr(sys, "argv", ["tradurre", "--version"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert capsys.readouterr().out.split() == ["tradurre", version("tradurre")]
