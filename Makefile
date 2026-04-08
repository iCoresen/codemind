.PHONY: install api cli test arq

install:
	python -m pip install -r requirements.txt

api:
	python -m app.main

cli:
	python -m app.cli

test:
	python -m pytest tests/

arq:
	arq -A app.arq_app worker --loglevel=info
