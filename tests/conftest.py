"""Never let subscription tests notify an operator's real callback."""
import pytest

import subscription_notifications


@pytest.fixture(autouse=True)
def isolate_subscription_delivery(monkeypatch, tmp_path):
    monkeypatch.setenv("NEF_INTEGRATION_CONFIG", str(tmp_path / "missing-integration-config.json"))
    monkeypatch.setenv("NEF_SUBSCRIPTION_CONFIG", str(tmp_path / "missing-subscription-config.json"))
    monkeypatch.setattr(subscription_notifications, "EVENTS", {})
