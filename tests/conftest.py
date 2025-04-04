import pytest

@pytest.fixture(scope="module")
def sample_fixture():
    # Setup code for the fixture
    yield
    # Teardown code for the fixture