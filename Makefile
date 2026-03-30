.PHONY: install api cli

install:
	python -m pip install -r requirements.txt

api:
	python -m app.main

cli:
	python -m app.cli
