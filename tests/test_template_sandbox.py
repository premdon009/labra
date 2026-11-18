"""EC-A08: every Jinja environment autoescapes and is sandboxed, so a value that reaches a
bill, report, receipt or screen can't run markup or reach Python internals."""

import pytest
from jinja2 import Environment
from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment

from labra.printing import templates as documents
from labra.web.templating import templates as screens

ENVIRONMENTS = {"screens and bills": screens.env, "reports and labels": documents._env}  # pyright: ignore[reportPrivateUsage]


@pytest.mark.item("EC-A08")
@pytest.mark.parametrize("name", ENVIRONMENTS)
def test_environment_is_sandboxed(name: str) -> None:
    assert isinstance(ENVIRONMENTS[name], SandboxedEnvironment)


@pytest.mark.item("EC-A08")
@pytest.mark.parametrize("name", ENVIRONMENTS)
def test_template_cannot_reach_python_internals(name: str) -> None:
    env: Environment = ENVIRONMENTS[name]
    with pytest.raises(SecurityError):
        env.from_string("{{ value.__class__.__mro__[1].__subclasses__() }}").render(value="x")


@pytest.mark.item("EC-A08")
@pytest.mark.parametrize("name", ENVIRONMENTS)
def test_values_are_escaped(name: str) -> None:
    env: Environment = ENVIRONMENTS[name]
    html = env.from_string("<td>{{ value }}</td>").render(value="<script>alert(1)</script>")
    assert html == "<td>&lt;script&gt;alert(1)&lt;/script&gt;</td>"
