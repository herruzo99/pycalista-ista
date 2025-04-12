# Contributing to PyCalista-ista

We welcome contributions to improve PyCalista-ista! Please follow these guidelines.

## Setting Up Integrations (Optional)

### Codecov

1.  Go to [Codecov](https://codecov.io/) and sign in with GitHub.
2.  Add the repository to Codecov.
3.  Coverage reports will be automatically uploaded by GitHub Actions on pushes/PRs to the main branch. No token is needed for public repositories.

### PyPI and TestPyPI

1.  Create accounts on [PyPI](https://pypi.org/) and [TestPyPI](https://test.pypi.org/).
2.  Generate API tokens scoped to this project:
    * TestPyPI token: https://test.pypi.org/manage/account/token/
    * PyPI token: https://pypi.org/manage/account/token/
3.  Add tokens to GitHub repository secrets (Settings → Secrets and variables → Actions):
    * `TEST_PYPI_API_TOKEN` with TestPyPI token.
    * `PYPI_API_TOKEN` with PyPI token.
    * *Note: Only maintainers need to do this.*

### OpenSSF Best Practices

1.  Go to [OpenSSF Best Practices](https://www.bestpractices.dev/).
2.  Sign in and add your repository.
3.  Follow their recommendations to improve the score.

## Contribution Requirements

### Code Standards

All contributions must adhere to these standards:

1.  **Code Style**:
    * Follow [PEP 8](https://peps.python.org/pep-0008/) style guide.
    * Use [Black](https://black.readthedocs.io/) code formatter (run `black .`).
    * Sort imports using [isort](https://pycqa.github.io/isort/) (run `isort .`).
    * Use [Ruff](https://beta.ruff.rs/docs/) for linting (run `ruff check .`).
2.  **Asynchronous Code**:
    * The library core (`virtual_api.py`, `pycalista_ista.py`) must use `asyncio` and `aiohttp`.
    * Follow async best practices.
3.  **Documentation**:
    * All new public functions/classes/methods must have docstrings following [Google style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings).
    * Update `README.md` and files in `docs/` if adding/changing features or usage.
    * Include `async`/`await` in examples.
4.  **Testing**:
    * All new code must include tests using `pytest` and `pytest-asyncio`.
    * Mock external `aiohttp` requests using `aresponses` or similar libraries.
    * Maintain or improve code coverage (`pytest --cov`).
    * Tests must cover success paths, error conditions (login, connection, parsing, API errors), and edge cases.
5.  **Type Hints**:
    * Use type hints for all function arguments and return values ([PEP 484](https://peps.python.org/pep-0484/)).
    * Aim for `mypy --strict` compliance (run `mypy pycalista_ista tests`).
6.  **Commit Messages**:
    * Follow [Conventional Commits](https://www.conventionalcommits.org/) format (e.g., `feat: Add support for device X`, `fix: Correct parsing error`).
    * Include issue number if applicable (e.g., `fix: Resolve login issue (#12)`).

### Development Setup

1.  Clone the repository: `git clone https://github.com/herruzo99/pycalista-ista.git && cd pycalista-ista`
2.  Create and activate a virtual environment: `python -m venv .venv && source .venv/bin/activate`
3.  Install in editable mode with development dependencies: `pip install -e ".[dev]"`
4.  Install pre-commit hooks (optional): `pre-commit install`

### Pull Request Process

1.  Fork the repository and create your feature branch from `main`.
2.  Make your changes, adhering to the code standards.
3.  Add or update tests for your changes.
4.  Ensure all tests pass: `pytest`
5.  Check formatting, linting, and types: `black .`, `isort .`, `ruff check .`, `mypy pycalista_ista tests` (or run `pre-commit run --all-files`).
6.  Commit your changes using the Conventional Commits format.
7.  Push your branch to your fork.
8.  Open a Pull Request against the `main` branch of the original repository.
9.  Clearly describe your changes in the Pull Request description.

## Creating Releases (Maintainers)

1.  Ensure `main` branch is up-to-date and all checks pass.
2.  Update version number in `pycalista_ista/__version__.py` and `setup.py`.
3.  Update `CHANGELOG.md` (if maintained).
4.  Commit version bump: `git commit -m "chore: Bump version to vX.Y.Z"`
5.  Create and push tag: `git tag -a vX.Y.Z -m "Release version X.Y.Z" && git push origin vX.Y.Z`
6.  Create a release on GitHub based on the tag.
7.  The GitHub Actions workflow should automatically build and publish to TestPyPI and PyPI upon tag creation. Monitor the action run.
