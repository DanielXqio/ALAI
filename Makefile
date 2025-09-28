.PHONY: build-ggwave setup serve

build-ggwave:
	cmake -S . -B build
	cmake --build build --target ggwave-cli

setup:
	python -m venv .venv
	.venv/bin/pip install -r requirements.txt

serve:
	uvicorn app.main:app --reload
