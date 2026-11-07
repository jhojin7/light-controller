PYTHON ?= python3

.PHONY: check package test e2e e2e-live e2e-sleep

check:
	$(PYTHON) scripts/check.py

package:
	$(PYTHON) scripts/package.py

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

e2e:
	$(PYTHON) scripts/e2e.py --prove-tests

e2e-live:
	$(PYTHON) scripts/e2e.py --live --prove-tests

e2e-sleep:
	$(PYTHON) scripts/e2e_sleep.py
