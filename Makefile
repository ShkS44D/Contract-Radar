PYTHON ?= python

.PHONY: install run test integration lint format lock
install:
	$(PYTHON) -m pip install -r requirements-dev.lock
	$(PYTHON) -m pip install --no-deps -e .
run:
	$(PYTHON) app.py
test:
	$(PYTHON) -m pytest --cov=sentinel.scanner --cov-report=term-missing
integration:
	SENTINEL_RUN_INTEGRATION=1 $(PYTHON) -m pytest tests/test_integration.py -q
lint:
	$(PYTHON) -m ruff check sentinel tests scripts app.py
	$(PYTHON) -m ruff format --check sentinel tests scripts app.py
	$(PYTHON) -m mypy
format:
	$(PYTHON) -m ruff check --fix sentinel tests scripts app.py
	$(PYTHON) -m ruff format sentinel tests scripts app.py
lock:
	$(PYTHON) scripts/lock.py
