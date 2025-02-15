# Contributing to PyCalista-ista

## Setting Up Integrations

### Codecov

1. Go to [Codecov](https://codecov.io/) and sign in with GitHub
2. Add repository to Codecov
3. Coverage reports will be automatically uploaded by GitHub Actions
4. No token needed for public repositories

### PyPI and TestPyPI

1. Create accounts on [PyPI](https://pypi.org/) and [TestPyPI](https://test.pypi.org/)
2. Generate API tokens:
   - TestPyPI token: https://test.pypi.org/manage/account/token/
   - PyPI token: https://pypi.org/manage/account/token/
3. Add tokens to GitHub repository secrets:
   - Go to Settings → Secrets and variables → Actions
   - Add `TEST_PYPI_API_TOKEN` with TestPyPI token
   - Add `PYPI_API_TOKEN` with PyPI token

### OpenSSF Best Practices

1. Go to [OpenSSF Best Practices](https://www.bestpractices.dev/)
2. Sign in and add your repository
3. Follow their recommendations to improve score

## Contribution Requirements

### Code Standards

All contributions must follow these standards:

1. Code Style:
   - Follow [PEP 8](https://peps.python.org/pep-0008/) style guide
   - Use [Black](https://black.readthedocs.io/) code formatter with default settings
   - Sort imports using [isort](https://pycqa.github.io/isort/) with Black compatibility

2. Documentation:
   - All new functions/classes must have docstrings following [Google style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
   - Update README.md if adding new features
   - Include docstring examples for public APIs

3. Testing:
   - All new code must include tests
   - Maintain or improve code coverage
   - Tests must follow [pytest](https://docs.pytest.org/) best practices

4. Type Hints:
   - Use type hints for all function arguments and return values
   - Follow [PEP 484](https://peps.python.org/pep-0484/) guidelines

5. Commit Messages:
   - Follow [Conventional Commits](https://www.conventionalcommits.org/) format
   - Include issue number if applicable

### Pull Request Process

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
   pip install pytest pytest-cov requests-mock black isort
   ```
4. Make your changes
5. Run tests and formatting:
   ```bash
   # Format code
   black .
   isort .
   
   # Run tests
   pytest --cov
   ```
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Creating Releases

1. Update version in:
   - setup.py
   - pyproject.toml
   - pycalista_ista/__version.py

2. Create and push tag:
   ```bash
   git tag -a v0.1.0 -m "Release version 0.1.0"
   git push origin v0.1.0
   ```

3. Create release on GitHub:
   - Go to Releases → Create new release
   - Choose the tag
   - Describe the changes
   - Publish release

4. The GitHub Action will automatically:
   - Run tests
   - Publish to TestPyPI
   - Test installation
   - Publish to PyPI
