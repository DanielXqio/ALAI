.PHONY: build-ggwave setup serve

build-ggwave:
	cmake -S external/ggwave -B external/ggwave/build
	cmake --build external/ggwave/build --config Release

setup:
	python -m venv .venv
	.venv/bin/pip install -r requirements.txt

serve:
	uvicorn app.main:app --reload
