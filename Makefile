.PHONY: build-ggwave setup serve

build-ggwave:

setup:
	python -m venv .venv
	.venv/bin/pip install -r requirements.txt

serve:
	uvicorn app.main:app --reload
