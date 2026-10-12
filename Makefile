PYTHON ?= python

.PHONY: install run test integration lint format lock
install:
	$(PYTHON) -m pip install -r requirements-dev.lock
	$(PYTHON) -m pip install --no-deps -e .
run:
	$(PYTHON) app.py
test:
	$(PYTHON) -m pytest --cov=contract_radar.scanner --cov-report=term-missing
integration:
	CONTRACT_RADAR_RUN_INTEGRATION=1 $(PYTHON) -m pytest tests/test_integration.py -q
lint:
	$(PYTHON) -m ruff check contract_radar tests scripts app.py vercel_app.py
	$(PYTHON) -m ruff format --check contract_radar tests scripts app.py vercel_app.py
	$(PYTHON) -m mypy
format:
	$(PYTHON) -m ruff check --fix contract_radar tests scripts app.py vercel_app.py
	$(PYTHON) -m ruff format contract_radar tests scripts app.py vercel_app.py
lock:
	$(PYTHON) scripts/lock.py
