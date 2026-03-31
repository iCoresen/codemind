.PHONY: install api cli test celery

install:
	python -m pip install -r requirements.txt

api:
	python -m app.main

cli:
	python -m app.cli

test:
	python -m pytest tests/

celery:
	celery -A app.celery_app worker --loglevel=info
