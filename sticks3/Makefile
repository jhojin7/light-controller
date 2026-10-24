PYTHON ?= python3
PIO = .venv/bin/pio
PORT ?= /dev/cu.usbmodem101

.PHONY: setup build diagnostic check provision upload upload-data monitor e2e e2e-live
setup:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt
	$(PIO) pkg install -e sticks3
	$(PYTHON) scripts/native_tools.py
build:
	$(PIO) run -e sticks3
diagnostic:
	$(PIO) run -e diagnostic
check:
	$(PYTHON) scripts/check.py
provision:
	$(PYTHON) scripts/provision.py --config "$(CONFIG)" --settings "$(SETTINGS)" $(if $(CA),--ca-cert "$(CA)")
upload:
	$(PIO) run -e sticks3 -t upload --upload-port "$(PORT)"
upload-data:
	$(PIO) run -e sticks3 -t uploadfs --upload-port "$(PORT)"
monitor:
	$(PIO) device monitor --port "$(PORT)" --baud 115200
e2e:
	.venv/bin/python scripts/e2e.py --port "$(PORT)"
e2e-live:
	.venv/bin/python scripts/e2e.py --port "$(PORT)" --live
