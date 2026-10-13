PYTHON ?= python3

.PHONY: check package

check:
	$(PYTHON) scripts/check.py

package:
	$(PYTHON) scripts/package.py
